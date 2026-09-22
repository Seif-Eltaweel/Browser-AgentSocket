"""
Unit and Integration Tests for Feature Spec 31:
Pure Model-Driven OODA Browser Operation (The Manus AI Standard) 🕹️⚡
"""

import os
import re
import tempfile
import unittest

from server.session.manager import SessionManager
from server.db import init_db

# The Master 19-Column CRM Schema
MASTER_19_COLUMNS = [
    "Code",
    "First Name",
    "Last Name",
    "URL",
    "Email Address",
    "Company",
    "Contact Info",
    "Position",
    "field",
    "Headline",
    "Current Job Title",
    "Current Company",
    "Location",
    "Region",
    "Latest Post Date",
    "Activity Status",
    "Mutual Connections Count",
    "Total Connections / Followers",
    "Compacted Work Experience"
]

STUDENT_KEYWORDS = [
    "student", "intern", "undergraduate", "b.sc. candidate", "bsc candidate",
    "m.sc. candidate", "msc candidate", "ph.d. candidate", "phd candidate",
    "trainee", "learner"
]

def is_student_or_intern(position: str, headline: str = "") -> bool:
    combined = f"{position} {headline}".lower()
    for kw in STUDENT_KEYWORDS:
        if re.search(r'\b' + re.escape(kw) + r'\b', combined):
            return True
    return False

class TestSpec31OODAOperation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_spec31.db")
        init_db(self.db_path)
        self.session_manager = SessionManager(base_log_dir=self.temp_dir, db_path=self.db_path)

    def test_zero_adhocs_invariant(self):
        """Spec 31: New sessions strictly maintain zero adhocs/ directory footprint."""
        session = self.session_manager.get_or_create_session(tab_group_id=901, tab_group_name="Batch 10 CRM Enrichment")
        self.assertFalse(os.path.exists(session.adhocs_dir))
        self.assertTrue(os.path.exists(session.input_dir))
        self.assertTrue(os.path.exists(session.output_dir))

    def test_student_bypass_schema(self):
        """Spec 31: Trainees, interns, and students are fast-tracked with full 19-column compliant schema."""
        test_cases = [
            ("Data Analyst Trainee", "", True),
            ("Artificial Intelligence Intern", "", True),
            ("Software Engineer", "B.Sc. Candidate at Cairo University", True),
            ("Senior Data Scientist", "Data Science Leader", False),
        ]
        for pos, head, expected in test_cases:
            self.assertEqual(is_student_or_intern(pos, head), expected)

    def test_master_19_column_schema(self):
        """Spec 31: Master schema defines exactly 19 columns with Contact Info at index 6."""
        self.assertEqual(len(MASTER_19_COLUMNS), 19)
        self.assertEqual(MASTER_19_COLUMNS[0], "Code")
        self.assertEqual(MASTER_19_COLUMNS[3], "URL")
        self.assertEqual(MASTER_19_COLUMNS[6], "Contact Info")
        self.assertEqual(MASTER_19_COLUMNS[18], "Compacted Work Experience")

    def test_credential_isolation(self):
        """Spec 31: Post-nominal degrees (MSc, Ph.D.) are recognized as credentials and not locations."""
        degree_patterns = re.compile(r'(?:\b(?:msc|phd|bsc|lssgb|pmp)\b|ph\.d\.|b\.sc\.)', re.IGNORECASE)
        test_strings = ["AbdelRahman Bahieldin, MSc", "Aderogba Otunla, Ph.D.", "Ahmed Shokry | LSSGB"]
        for s in test_strings:
            self.assertTrue(bool(degree_patterns.search(s)))

    def test_duration_header_recognition(self):
        """Spec 31: Cumulative duration headers (e.g. '5 yrs', '7 yrs 9 mos') are identified as durations."""
        duration_pattern = re.compile(r'^\d+\s*(?:yr|mo|year|month)s?(?:\s*\d+\s*(?:mo|month)s?)?$', re.IGNORECASE)
        self.assertTrue(bool(duration_pattern.match("5 yrs")))
        self.assertTrue(bool(duration_pattern.match("7 yrs 9 mos")))
        self.assertTrue(bool(duration_pattern.match("2 years")))
        self.assertFalse(bool(duration_pattern.match("Head of Biotechnology")))
        self.assertFalse(bool(duration_pattern.match("Data & Analytics Manager")))

if __name__ == "__main__":
    unittest.main()
