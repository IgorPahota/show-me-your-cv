import google.generativeai as genai
from django.conf import settings
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.units import inch
import io
import textwrap

class GeminiService:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-pro')

    def generate_resume(self, job_description):
        """Generate a resume based on the job description."""
        prompt = f"""
        Create a professional resume tailored for the following job description:
        {job_description}

        Format the resume with the following sections:
        1. Professional Summary
        2. Key Skills
        3. Work Experience (create 2-3 relevant positions)
        4. Education
        5. Certifications (if relevant)

        Make sure the experience and skills align perfectly with the job requirements.
        Keep it professional and realistic.
        """

        try:
            response = self.model.generate_content(prompt)
            resume_text = response.text
            return resume_text
        except Exception as e:
            raise Exception(f"Failed to generate resume: {str(e)}")

    def create_pdf(self, resume_text):
        """Convert the resume text to a PDF file."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter,
                              rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=72)

        styles = getSampleStyleSheet()
        story = []

        # Custom style for sections
        section_style = ParagraphStyle(
            'SectionStyle',
            parent=styles['Heading1'],
            fontSize=14,
            spaceAfter=12
        )

        # Custom style for content
        content_style = ParagraphStyle(
            'ContentStyle',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=6
        )

        # Split the text into sections and format
        sections = resume_text.split('\n\n')
        for section in sections:
            if section.strip():
                # Check if it's a section header
                if any(section.strip().startswith(header) for header in 
                      ['Professional Summary', 'Key Skills', 'Work Experience', 'Education', 'Certifications']):
                    p = Paragraph(section, section_style)
                else:
                    p = Paragraph(section, content_style)
                story.append(p)

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes 