import re
from typing import Iterator

class TextChunker:
    """
    A utility class to split a long text into smaller chunks based on a maximum length,
    while attempting to preserve natural boundaries like paragraphs, sentences, and words.
    """

    def __init__(self, max_length: int = 4000):
        """
        Initializes the TextChunker.

        Args:
            max_length: The maximum character length for any given chunk.
        """
        if max_length <= 0:
            raise ValueError("max_length must be a positive integer.")
        self.max_length = max_length

    def chunk(self, text: str) -> Iterator[str]:
        """
        Splits the text into chunks and yields each chunk.

        This method is a generator, which is memory-efficient for very long texts.

        Args:
            text: The input text to be chunked.

        Yields:
            A string chunk that is less than or equal to max_length.
        """
        if not text:
            return

        # Split the text by paragraphs first to maintain the larger structure
        paragraphs = text.split('\n\n')
        
        current_chunk = ""
        for paragraph in paragraphs:
            # If the paragraph itself is larger than the max length, it needs to be split
            if len(paragraph) > self.max_length:
                # If there's content in the current chunk, yield it before processing the long paragraph
                if current_chunk:
                    yield current_chunk.strip()
                    current_chunk = ""
                
                # Yield the sub-chunks from the oversized paragraph
                yield from self._split_long_paragraph(paragraph)
            
            # If adding the next paragraph fits, append it
            elif len(current_chunk) + len(paragraph) + 2 <= self.max_length:
                current_chunk += paragraph + '\n\n'
            
            # Otherwise, yield the current chunk and start a new one with the current paragraph
            else:
                yield current_chunk.strip()
                current_chunk = paragraph + '\n\n'
        
        # Yield any remaining content in the last chunk
        if current_chunk:
            yield current_chunk.strip()

    def _split_long_paragraph(self, paragraph: str) -> Iterator[str]:
        """
        Splits a paragraph that is longer than max_length, first by sentence, then by word.
        """
        # Use regex to split by sentences, keeping the delimiters
        sentences = re.split(r'(?<=[.!?])\s+', paragraph)
        
        current_chunk = ""
        for sentence in sentences:
            if len(sentence) > self.max_length:
                # This sentence is too long, so it must be split by words
                if current_chunk:
                    yield current_chunk.strip()
                    current_chunk = ""
                yield from self._split_long_sentence(sentence)

            elif len(current_chunk) + len(sentence) + 1 <= self.max_length:
                current_chunk += sentence + ' '
            else:
                yield current_chunk.strip()
                current_chunk = sentence + ' '
        
        if current_chunk:
            yield current_chunk.strip()

    def _split_long_sentence(self, sentence: str) -> Iterator[str]:
        """
        Splits a sentence that is longer than max_length, first by word, then by character.
        """
        words = sentence.split(' ')
        
        current_chunk = ""
        for word in words:
            if len(word) > self.max_length:
                # This word is too long, so it must be hard-split
                if current_chunk:
                    yield current_chunk.strip()
                    current_chunk = ""
                
                # Hard-split the oversized word
                for i in range(0, len(word), self.max_length):
                    yield word[i:i + self.max_length]

            elif len(current_chunk) + len(word) + 1 <= self.max_length:
                current_chunk += word + ' '
            else:
                yield current_chunk.strip()
                current_chunk = word + ' '
        
        if current_chunk:
            yield current_chunk.strip()
