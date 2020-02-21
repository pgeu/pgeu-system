#!/usr/bin/env python3

import sys
import json
import csv
import datetime
from decimal import Decimal


class BankFileParser(object):
    MANDATORY_ATTRIBUTES = ['date', 'amount', 'text']

    def __init__(self, spec):
        self.spec = spec

    def parse(self, contents):
        if self.spec['type'] == 'delimited':
            yield from self.parse_delimited(contents)
        else:
            raise Exception("Unknown type %s" % self.spec['type'])

    def parse_delimited(self, contents):
        reader = csv.reader(contents.splitlines(), delimiter=self.spec['delimiter'])

        toskip = self.spec.get('skiprows', 0)
        if self.spec['firstisheader']:
            foundheader = False
        else:
            # Pretend like it's already found
            foundheader = True

        for row in reader:
            if toskip > 0:
                toskip -= 1
                continue

            if not foundheader:
                # This is the header. If we're not supposed to validate it, just skip, but
                # otherwise validate each column.
                if self.spec['validateheader']:
                    if len(self.spec['columns']) != len(row):
                        raise Exception("Found {} columns in header, expected {}".format(len(row), len(self.spec['columns'])))
                    for col, header in zip(self.spec['columns'], row):
                        if header not in col['header']:
                            raise Exception("Column {} in file was supposed to be one of {}".format(header, col['header']))

                foundheader = True
                continue

            if not row:
                # Completely empty row?
                continue

            # Now parse the actual data
            obj = {
                'other': {},
                'validate': {},
            }
            for col, val in zip(self.spec['columns'], row):
                if col['function'] == 'ignore':
                    continue
                elif col['function'] == 'uniqueid':
                    obj['uniqueid'] = str(self.parse_value(col, val))
                elif col['function'] == 'date':
                    obj['date'] = self.parse_value(col, val, 'date')
                elif col['function'] == 'text':
                    obj['text'] = str(self.parse_value(col, val))
                elif col['function'] == 'amount':
                    obj['amount'] = self.parse_value(col, val, 'decimal')
                elif col['function'] == 'balance':
                    obj['balance'] = self.parse_value(col, val, 'decimal')
                elif col['function'] == 'validate':
                    obj['validate'][col['header'][0].lower()] = {
                        'val': str(self.parse_value(col, val)),
                        'validate': col['validate'].lower(),
                    }
                    # We also store the validated values, for possible future
                    # needs.
                    obj['other'][col['header'][0].lower()] = self.parse_value(col, val)
                elif col['function'] == 'store':
                    obj['other'][col['header'][0].lower()] = self.parse_value(col, val)
                else:
                    raise Exception("Unknown column function {}".format(col['function']))

            for a in self.MANDATORY_ATTRIBUTES:
                if a not in obj:
                    raise Exception("Mandatory attribute {} not found".format(a))

            if int(self.spec.get('delayincomingdays', '0')) > 0:
                # Any *incoming* transactions are delayed for <n> days before they are
                # loaded, to handle some banks that initially give partial information
                # about the transactions and backfill it later with no other changes.
                if obj['amount'] > 0:
                    if (datetime.datetime.today().date() - obj['date']).days < int(self.spec['delayincomingdays']):
                        # Just ignore the row, don't report it as error
                        continue

            yield obj

    def parse_value(self, col, val, mustbeformat=None):
        if mustbeformat and col.get('format', '**unknown**') != mustbeformat:
            raise Exception("Column {} must be format {}".format(col['header'][0], mustbefornat))

        if 'format' in col:
            if col['format'] == 'decimal':
                if col.get('decimal', '.') != '.':
                    return Decimal(val.replace(col['decimal'], '.'))
                else:
                    return Decimal(val)
            elif col['format'] == 'date':
                return datetime.datetime.strptime(val, col['dateformat']).date()
            else:
                raise Exception("Unknown column format {}".format(col['format']))
        else:
            # Just treat it as a string
            return str(val)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: bankfile.py <definition.json> <import.txt>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        parser = BankFileParser(json.load(f))

    with open(sys.argv[2], "rb") as f:
        for obj in parser.parse(f):
            print(obj)
