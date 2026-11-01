import io
import unittest
import zipfile

from shepard.internship_tools import extract_resume_text, score_internship


class InternshipToolsTests(unittest.TestCase):
    def test_extracts_docx_resume_text(self):
        buffer = io.BytesIO()
        document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:t>Ivan Tekenah</w:t></w:r></w:p>
          <w:p><w:r><w:t>Software student with Python, Java, SQL, and project experience building reliable applications.</w:t></w:r></w:p></w:body>
        </w:document>"""
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("word/document.xml", document)
        text = extract_resume_text("resume.docx", buffer.getvalue())
        self.assertIn("Ivan Tekenah", text)
        self.assertIn("Python", text)

    def test_scores_only_internship_like_jobs(self):
        resume = "Python SQL Java web applications and software engineering projects"
        scored = score_internship(
            {
                "title": "Software Engineering Intern",
                "description": "Build Python services and use SQL with the engineering team.",
                "location": "Remote",
            },
            resume_text=resume,
            search_terms=["Python", "SQL", "Software Engineering"],
            location="Remote",
        )
        self.assertIsNotNone(scored)
        self.assertGreaterEqual(scored[0], 55)
        self.assertIsNone(score_internship(
            {"title": "Senior Engineer", "description": "Ten years required", "location": "Remote"},
            resume_text=resume,
            search_terms=["Python"],
        ))

    def test_role_and_location_evidence_beat_a_structured_feed_bonus(self):
        resume = "Python SQL JavaScript web development and software engineering projects"
        relevant = score_internship(
            {
                "title": "Web Developer Intern",
                "description": "Build web applications with JavaScript and Python.",
                "location": "Remote in the United States",
                "source": "Remotive",
            },
            resume_text=resume,
            search_terms=["Python", "JavaScript", "SQL"],
            query="Web Development Intern",
            target_roles=["Software Engineering Intern"],
            location="Remote, Buffalo",
        )
        unrelated = score_internship(
            {
                "title": "Cybersecurity Compliance Intern",
                "description": "Review policies and audit controls.",
                "location": "London, United Kingdom",
                "source": "SimplifyJobs / Pitt CSC",
            },
            resume_text=resume,
            search_terms=["Python", "JavaScript", "SQL"],
            query="Web Development Intern",
            target_roles=["Software Engineering Intern"],
            location="Remote, Buffalo",
        )
        self.assertIsNotNone(relevant)
        self.assertIsNotNone(unrelated)
        self.assertGreaterEqual(relevant[0], 55)
        self.assertLess(unrelated[0], 55)
        self.assertGreater(relevant[0], unrelated[0])
        self.assertIn("location preference matches", relevant[1])

    def test_research_internships_can_surface_from_role_alignment(self):
        scored = score_internship(
            {
                "title": "Undergraduate Data Research Intern",
                "description": "Research data systems and build Python analysis tools.",
                "location": "Buffalo, New York",
                "source": "Public research program",
            },
            resume_text="Python data analysis software projects",
            search_terms=["Python", "data analysis"],
            query="Data Research Intern",
            location="Buffalo, Remote",
        )
        self.assertIsNotNone(scored)
        self.assertGreaterEqual(scored[0], 55)
        self.assertIn("local evidence ranking", scored[1])


if __name__ == "__main__":
    unittest.main()
