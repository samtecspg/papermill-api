import re
import traceback
import sqlite3
import os
from subprocess import check_output
import unittest


class CredentialsTestCase(unittest.TestCase):

    def test_no_keys(self):

        clean = True

        # Search for access key IDs: (?<![A-Z0-9])[A-Z0-9]{20}(?![A-Z0-9]).
        # In English, this regular expression says: Find me 20-character, uppercase,
        # alphanumeric strings that don’t have any uppercase, alphanumeric characters immediately before or after.

        # Search for secret access keys: (?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=]).
        # In English, this regular expression says: Find me 40-character, base-64 strings that don’t
        # have any base 64 characters immediately before or after.

        key_id_regex = '(?<![A-Z0-9])[A-Z0-9]{20}(?![A-Z0-9])'
        key_regex = '(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])'

        ls_files = check_output(["git", "ls-files", "--full-name"]).decode().strip("\n").split()
        print(ls_files)

        # UnicodeDecodeError. Searches database separately.
        excluded = ["app/main/data.sqlite",
                    "docs/img/enable_parameters.gif",
                    "docs/img/output_parameters.png"]

        ls_files[:] = [file for file in ls_files if file not in excluded]

        try:

            for file in ls_files:
                    if os.path.isfile(file):
                        with open(file, 'r') as f:
                            for idx, line in enumerate(f):
                                key_matches = re.findall(key_regex, line)
                                key_id_matches = re.findall(key_id_regex, line)

                                if len(key_matches) > 0 or len(key_id_matches) > 0:

                                    print()
                                    print("Found in " + f.name + " line " + str(idx+1) + ":")
                                    print("Keys: " + str(key_matches))
                                    print("Key ID: " + str(key_id_matches))
                                    print()

                                    clean = False

            sqlitedb = "app/main/data.sqlite"

            if os.path.isfile(sqlitedb):

                with sqlite3.connect(sqlitedb) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    for tablerow in cursor.fetchall():
                        table = tablerow[0]
                        cursor.execute("SELECT * FROM {t}".format(t=table))
                        for row in cursor:
                            for field in row.keys():

                                value = str(row[field])

                                key_matches = re.findall(key_regex, value)
                                key_id_matches = re.findall(key_id_regex, str(row[field]))

                                if len(key_matches) > 0 or len(key_id_matches) > 0:
                                    print()
                                    print("Found in database table " + str(table) + "." + str(field) + " id=" + str(row[0]) + ":")
                                    print("Keys: " + str(key_matches))
                                    print("Key ID: " + str(key_id_matches))
                                    print()

                                    clean = False

        except Exception as e:
            import sys
            print("filename: " + file)
            print(traceback.format_exception(None, e, e.__traceback__), file=sys.stderr, flush=True)

            assert False

        assert clean
