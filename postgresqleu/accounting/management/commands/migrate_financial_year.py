"""
Management command to migrate journal entries to new financial year boundaries.

This is a one-time migration script for transitioning from calendar year
accounting to a different financial year start date (e.g., UK April 6).

Usage:
  python manage.py migrate_financial_year --check  # Dry run
  python manage.py migrate_financial_year --execute  # Actually migrate
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Max

from postgresqleu.accounting.models import Year, JournalEntry, IncomingBalance
from postgresqleu.accounting.fyear import date_to_fy, fy_start_date, fy_end_date, format_fy_label


class Command(BaseCommand):
    help = 'Migrate journal entries to new financial year boundaries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Dry run - show what would change without making changes'
        )
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Actually perform the migration'
        )

    def handle(self, *args, **options):
        if not options['check'] and not options['execute']:
            self.stdout.write(
                self.style.ERROR('You must specify either --check or --execute')
            )
            return

        # Find all entries that are in the wrong financial year
        mismatched = []
        for entry in JournalEntry.objects.all().order_by('year_id', 'date', 'seq'):
            correct_fy = date_to_fy(entry.date)
            if entry.year_id != correct_fy:
                mismatched.append({
                    'entry': entry,
                    'current_fy': entry.year_id,
                    'correct_fy': correct_fy,
                })

        if not mismatched:
            self.stdout.write(
                self.style.SUCCESS('No entries need migration - all entries are in correct financial years')
            )
            return

        # Group by migration direction for reporting
        by_migration = {}
        for m in mismatched:
            key = (m['current_fy'], m['correct_fy'])
            if key not in by_migration:
                by_migration[key] = []
            by_migration[key].append(m)

        self.stdout.write(
            self.style.WARNING(
                'Found {} entries needing migration:'.format(len(mismatched))
            )
        )
        self.stdout.write('')

        for (from_fy, to_fy), entries in sorted(by_migration.items()):
            self.stdout.write(
                '  {} -> {}: {} entries'.format(
                    format_fy_label(from_fy),
                    format_fy_label(to_fy),
                    len(entries)
                )
            )
            # Show first few entries
            for m in entries[:5]:
                entry = m['entry']
                self.stdout.write(
                    '    Entry {}-{:04d}: date={}'.format(
                        entry.year_id, entry.seq, entry.date
                    )
                )
            if len(entries) > 5:
                self.stdout.write('    ... and {} more'.format(len(entries) - 5))
            self.stdout.write('')

        # Check which source years would become empty
        source_years = set(m['current_fy'] for m in mismatched)
        years_to_delete = []
        for y in sorted(source_years):
            # Count entries that would remain (not being moved)
            remaining = JournalEntry.objects.filter(year_id=y).exclude(
                id__in=[m['entry'].id for m in mismatched if m['current_fy'] == y]
            ).count()
            balance_count = IncomingBalance.objects.filter(year_id=y).count()
            if remaining == 0 and balance_count == 0:
                years_to_delete.append(y)

        if years_to_delete:
            self.stdout.write('Years that will be deleted (becoming empty):')
            for y in years_to_delete:
                self.stdout.write('  {}'.format(format_fy_label(y)))
            self.stdout.write('')

        if options['check']:
            self.stdout.write(
                self.style.WARNING(
                    'This is a dry run. Use --execute to perform the migration.'
                )
            )
            return

        # Execute the migration
        self.stdout.write('')
        self.stdout.write('Executing migration...')

        with transaction.atomic():
            # First, create any missing years
            years_needed = set(m['correct_fy'] for m in mismatched)
            years_created = []
            for y in sorted(years_needed):
                year_obj, created = Year.objects.get_or_create(
                    year=y,
                    defaults={'isopen': False}
                )
                if created:
                    years_created.append(y)
                    self.stdout.write(
                        '  Created year {} (closed)'.format(format_fy_label(y))
                    )

            # Track entries moved per target year for sequence renumbering
            entries_by_target_year = {}
            for m in mismatched:
                target = m['correct_fy']
                if target not in entries_by_target_year:
                    entries_by_target_year[target] = []
                entries_by_target_year[target].append(m['entry'])

            # Move entries to correct years
            moved_count = 0
            for target_fy, entries in entries_by_target_year.items():
                # Get the current max sequence for the target year
                max_seq = JournalEntry.objects.filter(
                    year_id=target_fy
                ).aggregate(Max('seq'))['seq__max'] or 0

                # Sort entries by date and original sequence for consistent ordering
                entries.sort(key=lambda e: (e.date, e.seq))

                for entry in entries:
                    max_seq += 1
                    old_year = entry.year_id
                    old_seq = entry.seq
                    entry.year_id = target_fy
                    entry.seq = max_seq
                    entry.save()
                    moved_count += 1

                    if moved_count <= 10:
                        self.stdout.write(
                            '  Moved entry {}-{:04d} -> {}-{:04d} (date: {})'.format(
                                old_year, old_seq,
                                target_fy, max_seq,
                                entry.date
                            )
                        )

            if moved_count > 10:
                self.stdout.write('  ... {} more entries moved'.format(moved_count - 10))

            self.stdout.write('')
            self.stdout.write(
                self.style.SUCCESS('Successfully migrated {} entries'.format(moved_count))
            )

            # Check for IncomingBalance issues
            affected_years = set()
            for m in mismatched:
                affected_years.add(m['current_fy'])
                affected_years.add(m['correct_fy'])

            incoming_balances = IncomingBalance.objects.filter(
                year_id__in=affected_years
            ).count()

            if incoming_balances > 0:
                self.stdout.write('')
                self.stdout.write(
                    self.style.WARNING(
                        'WARNING: {} IncomingBalance records exist for affected years.'.format(
                            incoming_balances
                        )
                    )
                )
                self.stdout.write(
                    self.style.WARNING(
                        'You should review and potentially recalculate these balances:'
                    )
                )
                for y in sorted(affected_years):
                    count = IncomingBalance.objects.filter(year_id=y).count()
                    if count > 0:
                        self.stdout.write(
                            '  Year {}: {} incoming balance records'.format(
                                format_fy_label(y), count
                            )
                        )

            # Clean up empty years that entries were moved out of
            source_years = set(m['current_fy'] for m in mismatched)
            for y in sorted(source_years):
                entry_count = JournalEntry.objects.filter(year_id=y).count()
                balance_count = IncomingBalance.objects.filter(year_id=y).count()
                if entry_count == 0 and balance_count == 0:
                    Year.objects.filter(year=y).delete()
                    self.stdout.write(
                        '  Deleted empty year {}'.format(format_fy_label(y))
                    )

            self.stdout.write('')
            self.stdout.write('Migration complete. Please verify account balances.')
