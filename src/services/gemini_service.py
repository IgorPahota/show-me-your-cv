import google.generativeai as genai
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def adapt_template_resume(self, template_file, job_description):
        """Adapt LaTeX resume template for a specific job."""
        try:
            logger.info("Starting adapt_template_resume")
            
            if not template_file:
                logger.error("No template file provided")
                raise Exception("No template file provided")
            if not job_description:
                logger.error("No job description provided")
                raise Exception("No job description provided")

            # Read the LaTeX template
            logger.info("Reading template file")
            template_file.seek(0)
            latex_template = template_file.read().decode('utf-8')
            logger.info(f"Template content length: {len(latex_template)}")
            
            if not latex_template.strip():
                logger.error("Template file is empty")
                raise Exception("Template file is empty")
            
            logger.info("Creating prompt")
            prompt = f"""You are a professional resume editor. Your task is to adapt this LaTeX resume for a specific job.

            Job Description:
            {job_description}

            Current Resume Template (in LaTeX):
            {latex_template}

            Instructions:
            1. Keep the EXACT same LaTeX preamble (documentclass, packages, etc.) from the template
            2. Keep the EXACT same document structure and environments
            3. Only modify the content inside sections to match the job requirements
            4. Do not change any formatting commands or document settings
            5. Ensure all LaTeX environments remain properly closed
            6. Return the COMPLETE LaTeX document

            IMPORTANT:
            - Copy and use the EXACT same \\\\documentclass line from the template
            - Copy and use ALL the same \\\\usepackage commands from the template
            - Keep ALL the same formatting definitions from the template
            - Maintain the EXACT same document structure
            - End with \\\\end{{document}}
            - Do not add any explanations or markdown formatting
            - Return ONLY the LaTeX code

            If you cannot generate a valid response, return an error message starting with 'ERROR:'."""

            logger.info("Calling LLM")
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,  # Lower temperature for more precise copying
                    "candidate_count": 1,
                    "max_output_tokens": 2048,
                    "top_p": 0.8,
                    "top_k": 40,
                }
            )
            logger.info("Got response from LLM")
            
            if not response or not response.candidates:
                logger.error("No response generated from LLM")
                raise Exception("No response generated from LLM")
                
            if not response.candidates[0].content or not response.candidates[0].content.parts:
                logger.error("Empty response from LLM")
                raise Exception("Empty response from LLM")
            
            latex_content = response.candidates[0].content.parts[0].text.strip()
            logger.info(f"Generated content length: {len(latex_content)}")
            
            if not latex_content:
                logger.error("Generated LaTeX content is empty")
                raise Exception("Generated LaTeX content is empty")
                
            if latex_content.startswith('ERROR:'):
                logger.error(f"LLM returned error: {latex_content}")
                raise Exception(latex_content[6:].strip())
            
            # Remove any markdown code block indicators
            latex_content = latex_content.replace('```latex', '').replace('```', '').strip()
            logger.info("Successfully generated LaTeX content")
            
            return latex_content
                    
        except Exception as e:
            logger.error(f"Error in adapt_template_resume: {str(e)}")
            raise Exception(f"Failed to adapt resume template: {str(e)}")

    def create_pdf(self, resume_text):
        """Legacy method - kept for backward compatibility."""
        pass 