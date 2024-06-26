# Generated by Django 3.2.14 on 2024-04-08 10:26

from django.db import migrations, models
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ('confsponsor', '0028_sponsorshipbenefit_deadline'),
    ]

    operations = [
        migrations.AddField(
            model_name='sponsorclaimedbenefit',
            name='claimnum',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='sponsorshipbenefit',
            name='maxclaims',
            field=models.IntegerField(default=1, verbose_name='Max number of claims', help_text="Maximum number of times this benefit can be claimed", validators=[MinValueValidator(1)]),
        ),
        migrations.AlterUniqueTogether(
            name='sponsorclaimedbenefit',
            unique_together={},
        ),
        migrations.AddConstraint(
            model_name='sponsorclaimedbenefit',
            constraint=models.UniqueConstraint(
                name='uniq_sponsor_benefit_num',
                fields=('sponsor', 'benefit', 'claimnum'),
                deferrable=models.Deferrable.DEFERRED,
            ),
        )
    ]
