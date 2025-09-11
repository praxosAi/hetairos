import asyncio
from typing import Dict, Optional, Tuple
import magic  # python-magic for file type detection

class FileProcessor:
    """Processes different file types for content extraction and Praxos ingestion"""
    
    def __init__(self):
        self.supported_text_types = {
            'text/plain',
            'text/csv', 
            'text/html',
            'application/json',
            'application/xml',
            'text/xml'
        }
        
        self.supported_doc_types = {
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
    
    def should_process_file(self, filename: str, mimetype: str, file_size: int) -> Tuple[bool, str]:
        """Determine if file should be processed for content extraction"""
        
        # Skip very large files (>10MB)
        max_size = 10 * 1024 * 1024
        if file_size > max_size:
            return False, f"File too large: {file_size} bytes (max {max_size})"
        
        # Skip certain file types that don't contain useful text
        skip_types = {
            'image/', 'video/', 'audio/', 
            'application/zip', 'application/x-rar',
            'application/octet-stream'
        }
        
        for skip_type in skip_types:
            if mimetype.startswith(skip_type):
                return False, f"File type not suitable for text extraction: {mimetype}"
        
        # Process text files and documents
        if (mimetype in self.supported_text_types or 
            mimetype in self.supported_doc_types or
            mimetype.startswith('text/')):
            return True, "File suitable for processing"
        
        return False, f"Unsupported file type: {mimetype}"
    
    async def extract_content(self, file_data: bytes, filename: str, mimetype: str) -> Optional[str]:
        """Extract text content from file data"""
        
        try:
            # Handle text files
            if mimetype.startswith('text/') or mimetype in self.supported_text_types:
                return await self._extract_text_content(file_data, mimetype)
            
            # Handle PDF files
            elif mimetype == 'application/pdf':
                return await self._extract_pdf_content(file_data)
            
            # Handle Office documents
            elif mimetype in self.supported_doc_types:
                return await self._extract_office_content(file_data, mimetype)
            
            else:
                return None
                
        except Exception as e:
            print(f"Error extracting content from {filename}: {e}")
            return None
    
    async def _extract_text_content(self, file_data: bytes, mimetype: str) -> str:
        """Extract content from text files"""
        # Try different encodings
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                content = file_data.decode(encoding)
                # Basic cleanup for HTML
                if mimetype == 'text/html':
                    import re
                    # Remove HTML tags (basic cleanup)
                    content = re.sub(r'<[^>]+>', '', content)
                    content = re.sub(r'\s+', ' ', content).strip()
                
                return content
            except UnicodeDecodeError:
                continue
        
        raise UnicodeDecodeError("Could not decode file with any supported encoding")
    
    async def _extract_pdf_content(self, file_data: bytes) -> str:
        """Extract text from PDF files"""
        try:
            import PyPDF2
            import io
            
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_data))
            text_content = []
            
            # Extract text from each page (limit to first 10 pages for performance)
            max_pages = min(10, len(pdf_reader.pages))
            for page_num in range(max_pages):
                page = pdf_reader.pages[page_num]
                text_content.append(page.extract_text())
            
            content = '\n'.join(text_content).strip()
            
            # If no content extracted, indicate it's a non-text PDF
            if not content:
                return f"[PDF file with {len(pdf_reader.pages)} pages - no extractable text content]"
            
            return content
            
        except ImportError:
            print("PyPDF2 not installed, cannot extract PDF content")
            return f"[PDF file - content extraction not available]"
        except Exception as e:
            print(f"Error extracting PDF content: {e}")
            return f"[PDF file - extraction failed: {str(e)}]"
    
    async def _extract_office_content(self, file_data: bytes, mimetype: str) -> str:
        """Extract text from Office documents"""
        try:
            if mimetype == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                # Word document
                import docx
                import io
                
                doc = docx.Document(io.BytesIO(file_data))
                text_content = []
                
                for paragraph in doc.paragraphs:
                    text_content.append(paragraph.text)
                
                return '\n'.join(text_content).strip()
            
            elif mimetype in ['application/vnd.ms-excel', 
                             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                # Excel document
                import pandas as pd
                import io
                
                # Read first sheet only
                df = pd.read_excel(io.BytesIO(file_data), nrows=100)  # Limit rows
                
                # Convert to text representation
                return df.to_string(index=False)
            
            else:
                return f"[Office document - {mimetype} - content extraction not implemented]"
                
        except ImportError as e:
            print(f"Required library not installed for {mimetype}: {e}")
            return f"[Office document - content extraction not available]"
        except Exception as e:
            print(f"Error extracting Office content: {e}")
            return f"[Office document - extraction failed: {str(e)}]"
    
    def get_file_summary(self, filename: str, mimetype: str, file_size: int, content: str = None) -> str:
        """Generate a summary of the file for Praxos ingestion"""
        
        size_mb = file_size / (1024 * 1024)
        
        summary = f"File: {filename}\n"
        summary += f"Type: {mimetype}\n"
        summary += f"Size: {size_mb:.2f} MB\n"
        
        if content:
            # Truncate content for summary (first 500 chars)
            if len(content) > 500:
                summary += f"Content preview: {content[:500]}...\n"
                summary += f"[Full content: {len(content)} characters]"
            else:
                summary += f"Content: {content}"
        else:
            summary += "Content: [Binary file or extraction failed]"
        
        return summary