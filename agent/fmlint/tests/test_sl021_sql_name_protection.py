#!/usr/bin/env python3
"""Tests for SL021 — ExecuteSQL must protect table/field names via GetTN/GetFN/GTFN.

Run from the agentic-fm root:
    python3 -m unittest agent.fmlint.tests.test_sl021_sql_name_protection -v
    python3 agent/fmlint/tests/test_sl021_sql_name_protection.py
"""
import sys
import unittest
from pathlib import Path

# Make the agentic-fm root importable (this file is agent/fmlint/tests/…).
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.fmlint.config import LintConfig            # noqa: E402
from agent.fmlint.types import Severity               # noqa: E402
from agent.fmlint.formats.xml_parser import parse_xml_string        # noqa: E402
from agent.fmlint.rules.sl_inventory import (                       # noqa: E402
    _sl021_find_hardcoded,
    SqlMustProtectIdentifiers,
)
from agent.fmlint.rules.calculations import KnownFunction           # noqa: E402


def _idents(calc):
    return [i for i, _ in _sl021_find_hardcoded(calc)]


# A fully protected query — every identifier injected via GetFN/GetTN.
PROTECTED = (
    'ExecuteSQLe ( "SELECT " & GetFN ( DatabaseFile__x::FileName ; True ) '
    '& " FROM " & GetTN ( DatabaseFile__x::FileName ; True ) '
    '& " WHERE " & GetFN ( DatabaseFile__x::IsActive ; True ) & " = ?" '
    '; "" ; "" ; 1 )'
)


class TestSL021Parser(unittest.TestCase):
    """Unit tests on the detection helper (no XML / engine)."""

    def test_protected_query_is_clean(self):
        self.assertEqual(_sl021_find_hardcoded(PROTECTED), [])

    def test_hardcoded_table_flagged(self):
        calc = 'ExecuteSQL ( "SELECT " & GetFN ( T::F ; True ) & " FROM DatabaseFile" ; "" ; "" )'
        self.assertIn(("DatabaseFile", "FROM"), _sl021_find_hardcoded(calc))

    def test_hardcoded_table_and_fields_flagged(self):
        calc = 'ExecuteSQL ( "SELECT FileName FROM DatabaseFile WHERE IsActive = ?" ; "" ; "" ; 1 )'
        idents = _idents(calc)
        self.assertIn("FileName", idents)
        self.assertIn("DatabaseFile", idents)
        self.assertIn("IsActive", idents)

    def test_multi_field_select_list_flagged(self):
        calc = 'ExecuteSQL ( "SELECT a, b, c FROM " & GetTN ( T::F ; True ) ; "" ; "" )'
        self.assertEqual(set(_idents(calc)), {"a", "b", "c"})

    def test_join_table_flagged(self):
        calc = ('ExecuteSQL ( "SELECT " & GetFN ( T::F ; True ) & " FROM " '
                '& GetTN ( T::F ; True ) & " JOIN OtherTable ON x = y" ; "" ; "" )')
        self.assertIn(("OtherTable", "JOIN"), _sl021_find_hardcoded(calc))

    def test_count_star_and_functions_ok(self):
        calc = 'ExecuteSQL ( "SELECT COUNT(*) FROM " & GetTN ( T::F ; True ) ; "" ; "" )'
        self.assertEqual(_sl021_find_hardcoded(calc), [])

    def test_table_alias_not_flagged(self):
        # Injected table followed by an alias in the NEXT literal — the alias is
        # not in an identifier position within its literal, so no false positive.
        calc = ('ExecuteSQL ( "SELECT " & GetFN ( T::F ; True ) & " FROM " '
                '& GetTN ( T::F ; True ) & " t WHERE " & GetFN ( T::K ; True ) '
                '& " = ?" ; "" ; "" ; 1 )')
        self.assertEqual(_sl021_find_hardcoded(calc), [])

    def test_separators_and_binds_not_scanned(self):
        # A bind value that looks SQL-ish must be ignored — only the 1st arg is scanned.
        calc = ('ExecuteSQL ( "SELECT " & GetFN ( T::F ; True ) & " FROM " '
                '& GetTN ( T::F ; True ) ; "" ; "" ; "FROM nowhere" )')
        self.assertEqual(_sl021_find_hardcoded(calc), [])

    def test_no_executesql_means_no_findings(self):
        # A non-SQL string with the word FROM must not trip the rule.
        self.assertEqual(_sl021_find_hardcoded('Let ( ~x = "moved FROM here" ; ~x )'), [])

    def test_dedupes_repeats(self):
        calc = ('ExecuteSQL ( "SELECT FileName FROM DatabaseFile" ; "" ; "" ) '
                '& ExecuteSQL ( "SELECT FileName FROM DatabaseFile" ; "" ; "" )')
        # FileName + DatabaseFile, de-duplicated to one each
        self.assertEqual(len(_sl021_find_hardcoded(calc)), 2)


class TestSL021Engine(unittest.TestCase):
    """XML-path tests: parse a snippet, drive the rule's check_xml directly.

    Driving the rule directly (rather than the whole multi-rule engine loop)
    keeps the test scoped to SL021 + the C003 config, and avoids coupling to
    unrelated rules' behavior on a minimal snippet.
    """

    def _parse(self, calc):
        xml = (
            '<fmxmlsnippet type="FMObjectList">'
            '<Step enable="True" id="141" name="Set Variable">'
            '<Value><Calculation><![CDATA[' + calc + ']]></Calculation></Value>'
            '<Name>$x</Name>'
            '</Step>'
            '</fmxmlsnippet>'
        )
        return parse_xml_string(xml)

    def test_violation_is_error_severity(self):
        pr = self._parse('ExecuteSQL ( "SELECT FileName FROM DatabaseFile" ; "" ; "" )')
        sl = SqlMustProtectIdentifiers().check_xml(pr, None, None, LintConfig())
        self.assertTrue(sl, "SL021 should fire on a hardcoded query")
        self.assertEqual(sl[0].severity, Severity.ERROR)
        self.assertIn("DatabaseFile", sl[0].message)

    def test_protected_produces_no_sl021(self):
        pr = self._parse(PROTECTED)
        self.assertEqual(SqlMustProtectIdentifiers().check_xml(pr, None, None, LintConfig()), [])

    def test_c003_whitelists_protective_cfs(self):
        pr = self._parse(PROTECTED)
        cfg = LintConfig.load(_ROOT)  # loads the fork's fmlint.config.json (C003 extras)
        c003 = KnownFunction().check_xml(pr, None, None, cfg)
        noisy = [
            d for d in c003
            if any(fn in d.message for fn in ("GetFN", "GetTN", "GTFN", "ExecuteSQLe"))
        ]
        self.assertEqual(noisy, [], f"C003 must whitelist protective CFs: {[d.message for d in noisy]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
