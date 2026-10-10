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


if __name__ == "__main__":
    unittest.main()
