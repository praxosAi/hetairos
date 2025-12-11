import re
from typing import Iterator, List


class TelegramHTMLChunker:
    """
    Chunks HTML text while preserving tag integrity across chunk boundaries.

    Key features:
    - Respects natural boundaries (paragraphs, sentences, words)
    - Never breaks inside HTML tags
    - Tracks open tags and closes them at chunk end
    - Reopens tags at the start of next chunk
    - Special handling for code blocks

    Inspired by the existing TextChunker but adapted for HTML.
    """

    def __init__(self, max_length: int = 4000):
        """
        Initialize the HTML chunker.

        Args:
            max_length: Maximum characters per chunk (Telegram limit is 4096,
                       we use 4000 for safety margin)
        """
        if max_length <= 0:
            raise ValueError("max_length must be a positive integer.")
        self.max_length = max_length

    def chunk(self, html: str) -> Iterator[str]:
        """
        Split HTML text into chunks while preserving formatting.

        Args:
            html: HTML-formatted text to chunk

        Yields:
            HTML chunks with proper tag closure/reopening
        """
        if not html:
            return

        if len(html) <= self.max_length:
            yield html
            return

        start = 0
        while start < len(html):
            # Calculate potential chunk end
            end = start + self.max_length

            if end >= len(html):
                # Last chunk
                chunk = html[start:]
                yield chunk
                break

            # Find safe break point
            break_point = self._find_safe_break_point(html, start, end)

            # Extract chunk
            chunk = html[start:break_point]

            # Get tags that are open at break point
            open_tags = self._get_open_tags_at_position(html, break_point)

            # Close tags at end of chunk
            if open_tags:
                chunk += self._close_tags(open_tags)

            yield chunk

            # Move to next chunk
            start = break_point

            # Reopen tags at start of next chunk
            if start < len(html) and open_tags:
                reopened = self._reopen_tags(open_tags)
                # Insert reopened tags at the start of remaining text
                html = html[:start] + reopened + html[start:]

    def _find_safe_break_point(self, html: str, start: int, max_end: int) -> int:
        """
        Find optimal break point respecting HTML structure and natural boundaries.

        Priority:
        1. Don't break inside HTML tags (<...>)
        2. Don't break inside code blocks (<pre>...</pre>)
        3. Prefer paragraph breaks (\\n\\n)
        4. Then sentence breaks (.!? followed by space/newline)
        5. Then word breaks (space)
        6. Last resort: hard break at max_end

        Args:
            html: Full HTML text
            start: Start position of current chunk
            max_end: Maximum end position

        Returns:
            Optimal break position
        """
        # Check if we're inside a code block
        if self._is_inside_code_block(html, max_end):
            # Try to break after the code block
            code_end = html.find('</pre>', max_end)
            if code_end != -1 and code_end < start + self.max_length * 1.2:
                # Code block ends soon, include it
                return code_end + 6  # len('</pre>')
            else:
                # Code block is very long, try to break before it
                code_start = html.rfind('<pre', start, max_end)
                if code_start > start:
                    return code_start

        # Check if we're inside an HTML tag
        last_tag_open = html.rfind('<', start, max_end)
        last_tag_close = html.rfind('>', start, max_end)
        if last_tag_open > last_tag_close:
            # We're inside a tag, break before it
            return last_tag_open

        # Look for paragraph break (double newline)
        last_para = html.rfind('\n\n', start, max_end)
        if last_para > start:
            return last_para + 2  # Include the newlines

        # Look for sentence break
        for punct in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
            last_sentence = html.rfind(punct, start, max_end)
            if last_sentence > start:
                return last_sentence + len(punct)

        # Look for word break
        last_space = html.rfind(' ', start, max_end)
        if last_space > start:
            return last_space + 1

        # No good break point found, hard break at max_end
        return max_end

    def _get_open_tags_at_position(self, html: str, pos: int) -> List[str]:
        """
        Track which HTML tags are open at a given position.

        Uses a stack to track nested tags. Returns tags in opening order.

        Args:
            html: Full HTML text
            pos: Position to check

        Returns:
            List of open tag names, e.g., ['b', 'i', 'code']
        """
        tag_stack = []
        # Pattern matches opening and closing tags
        tag_pattern = re.compile(r'<(/?)(\w+)(?:\s[^>]*)?>''')

        for match in tag_pattern.finditer(html[:pos]):
            is_closing = match.group(1) == '/'
            tag_name = match.group(2)

            if is_closing:
                # Remove matching opening tag from stack
                if tag_stack and tag_stack[-1] == tag_name:
                    tag_stack.pop()
            else:
                # Add opening tag to stack
                # Only track tags that need closing
                if tag_name in ['b', 'i', 'u', 's', 'code', 'pre', 'a', 'strong', 'em']:
                    tag_stack.append(tag_name)

        return tag_stack

    def _close_tags(self, tags: List[str]) -> str:
        """
        Generate closing tags in reverse order.

        Args:
            tags: List of open tag names ['b', 'i', 'code']

        Returns:
            Closing tags string '</code></i></b>'
        """
        return ''.join(f'</{tag}>' for tag in reversed(tags))

    def _reopen_tags(self, tags: List[str]) -> str:
        """
        Generate opening tags in original order.

        Args:
            tags: List of tag names to reopen ['b', 'i', 'code']

        Returns:
            Opening tags string '<b><i><code>'
        """
        result = []
        for tag in tags:
            if tag == 'a':
                # Can't reopen <a> without href attribute
                # User will see link break across chunks (acceptable limitation)
                continue
            result.append(f'<{tag}>')
        return ''.join(result)

    def _is_inside_code_block(self, html: str, pos: int) -> bool:
        """
        Check if position is inside a <pre> block.

        Args:
            html: Full HTML text
            pos: Position to check

        Returns:
            True if inside code block
        """
        last_pre_open = html.rfind('<pre', 0, pos)
        last_pre_close = html.rfind('</pre>', 0, pos)
        return last_pre_open > last_pre_close
