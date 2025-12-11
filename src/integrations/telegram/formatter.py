import re
import html
import uuid
from typing import Dict


class TelegramHTMLFormatter:
    """
    Converts markdown-formatted text to Telegram-compatible HTML.

    The placeholder strategy is used to protect code blocks from being affected
    by other markdown conversions. For example, code like `def foo(**kwargs):`
    should not have the **kwargs** converted to bold.

    We extract code first, convert everything else, then restore the code.
    This ensures markdown-like syntax inside code blocks is preserved.

    Supports:
    - Bold: **text** or __text__ → <b>text</b>
    - Italic: *text* or _text_ → <i>text</i>
    - Code: `code` → <code>code</code>
    - Code blocks: ```code``` → <pre><code>code</code></pre>
    - Links: [text](url) → <a href="url">text</a>
    - Headers: # Header → <b>Header</b>
    - Lists: - item → • item
    """

    # Compile regex patterns at class level for performance
    CODE_BLOCK_PATTERN = re.compile(r'```(\w+\n)?(.*)```', re.DOTALL)
    INLINE_CODE_PATTERN = re.compile(r'`([^`\n]+)`')
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    BOLD_PATTERN = re.compile(r'\*\*(.+?)\*\*', re.DOTALL)
    # Simplified italic pattern - matches *text* but not **text** or URLs with underscores
    ITALIC_PATTERN = re.compile(r'(?<!\*)\*(?![*\s])(?:[^*]*[^*\s])?\*(?!\*)')
    HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    LIST_PATTERN = re.compile(r'^[-*]\s+(.+)$', re.MULTILINE)

    def _generate_unique_session_id(self, text: str) -> str:
        """
        Generate a unique session ID that doesn't collide with text content.

        Args:
            text: The text to check for collisions

        Returns:
            A unique session ID string
        """
        max_attempts = 100  # Prevent infinite loop
        for _ in range(max_attempts):
            session_id = uuid.uuid4().hex[:8]
            # Check if this session_id would create collisions
            if f'__CB{session_id}_' not in text and f'__IC{session_id}_' not in text:
                return session_id

        # Fallback to longer UUID if somehow we couldn't find a unique one
        return uuid.uuid4().hex

    def convert_markdown_to_html(self, text: str) -> str:
        """
        Convert markdown text to Telegram HTML format.

        Args:
            text: Input text with markdown formatting

        Returns:
            HTML-formatted text suitable for Telegram's parse_mode="HTML"
        """
        if not text:
            return text

        # Generate collision-free session ID
        session_id = self._generate_unique_session_id(text)
        code_blocks: Dict[str, str] = {}
        inline_codes: Dict[str, str] = {}

        # Step 1: Extract and convert code blocks
        # We do this FIRST to protect code from other markdown conversions
        # Example: ```python\ndef foo(**kwargs):\n    return x * y\n```
        # Without protection, **kwargs** would become <b>kwargs</b>
        def save_code_block(match):
            lang = match.group(1) or ''
            code = match.group(2)
            # Escape HTML in code
            escaped_code = html.escape(code.strip())
            placeholder = f'__CB{session_id}_{len(code_blocks)}__'
            if lang:
                code_blocks[placeholder] = f'<pre><code class="language-{html.escape(lang)}">{escaped_code}</code></pre>'
            else:
                code_blocks[placeholder] = f'<pre>{escaped_code}</pre>'
            return placeholder

        text = self.CODE_BLOCK_PATTERN.sub(save_code_block, text)

        # Step 2: Extract and convert inline code
        def save_inline_code(match):
            code = match.group(1)
            escaped_code = html.escape(code)
            placeholder = f'__IC{session_id}_{len(inline_codes)}__'
            inline_codes[placeholder] = f'<code>{escaped_code}</code>'
            return placeholder

        text = self.INLINE_CODE_PATTERN.sub(save_inline_code, text)

        # Step 3: Convert links BEFORE bold/italic to prevent URL parts being styled
        # This is critical - URLs often contain underscores that look like italic markers
        links = {}
        def save_link(match):
            link_text = match.group(1)
            url = match.group(2)
            # Escape link text
            escaped_text = html.escape(link_text)
            # Sanitize URL: escape quotes
            sanitized_url = url.replace('"', '&quot;').replace("'", '&apos;')
            placeholder = f'__LINK{session_id}_{len(links)}__'
            links[placeholder] = f'<a href="{sanitized_url}">{escaped_text}</a>'
            return placeholder

        text = self.LINK_PATTERN.sub(save_link, text)

        # Step 4: Convert bold
        def convert_bold(match):
            # Match group 1 for ** or group 2 for __
            content = match.group(1) if match.group(1) else match.group(2)
            # Escape HTML in content
            escaped = html.escape(content)
            return f'<b>{escaped}</b>'

        text = self.BOLD_PATTERN.sub(convert_bold, text)

        # Step 5: Convert italic (simplified - only single asterisks, not underscores in URLs)
        def convert_italic(match):
            content = match.group(1)
            # Escape HTML in content
            escaped = html.escape(content)
            return f'<i>{escaped}</i>'

        text = self.ITALIC_PATTERN.sub(convert_italic, text)

        # Step 6: Convert headers (line by line)
        def convert_header(match):
            level = len(match.group(1))
            content = match.group(2)
            # Escape if not already formatted
            if '<' not in content:
                content = html.escape(content)
            # Telegram doesn't support headers, use bold with newlines
            return f'<b>{content}</b>'

        text = self.HEADER_PATTERN.sub(convert_header, text)

        # Step 7: Convert lists
        def convert_list(match):
            content = match.group(1)
            # Content may already have HTML tags from bold/italic conversion
            return f'• {content}'

        text = self.LIST_PATTERN.sub(convert_list, text)

        # Step 8: Escape any remaining HTML in plain text
        # This is a safety net for any text that wasn't part of markdown
        text = self._escape_remaining_html(text, session_id)

        # Step 9: Restore code blocks
        for placeholder, html_code in code_blocks.items():
            text = text.replace(placeholder, html_code)

        # Step 10: Restore inline code
        for placeholder, html_code in inline_codes.items():
            text = text.replace(placeholder, html_code)

        # Step 11: Restore links
        for placeholder, html_link in links.items():
            text = text.replace(placeholder, html_link)

        return text

    def _escape_remaining_html(self, text: str, session_id: str) -> str:
        """
        Escape HTML characters in plain text while preserving our generated tags.

        Args:
            text: Text that may contain unescaped HTML
            session_id: Current session ID for placeholder matching

        Returns:
            Text with remaining HTML escaped
        """
        # Split by our known HTML tags to avoid escaping them
        tag_pattern = re.compile(r'(</?(?:b|i|u|s|code|pre|a)[^>]*>)')
        parts = tag_pattern.split(text)

        escaped_parts = []
        for i, part in enumerate(parts):
            # Odd indices are tags (from split with capturing group)
            if i % 2 == 1:
                # This is a tag, keep as-is
                escaped_parts.append(part)
            else:
                # This is text content between tags
                # Skip if it's a placeholder
                if f'__CB{session_id}_' not in part and f'__IC{session_id}_' not in part and f'__LINK{session_id}_' not in part:
                    # Only escape if not already escaped
                    if '&lt;' not in part and '&gt;' not in part:
                        part = html.escape(part, quote=False)
                escaped_parts.append(part)

        return ''.join(escaped_parts)
