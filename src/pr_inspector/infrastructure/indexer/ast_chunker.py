"""Python AST structure-aware code chunker."""

import ast

from pr_inspector.domain.entities import ChunkType, CodeChunk


class PythonAstChunker:
    """Parses Python code into structure-aware chunks using standard library ast."""

    def chunk_file(self, file_path: str, content: str) -> list[CodeChunk]:
        """Split Python source into function, class, and method chunks."""
        if not content.strip():
            return []

        lines = content.splitlines()
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            # Fallback gracefully for unparseable Python files
            return [
                CodeChunk(
                    id=f"{file_path}:1-{len(lines)}:syntax_error",
                    file_path=file_path,
                    content=content,
                    start_line=1,
                    end_line=len(lines),
                    chunk_type=ChunkType.TEXT_BLOCK,
                    language="python",
                )
            ]

        chunks: list[CodeChunk] = []

        # 1. Check for module preamble (docstrings, imports, top-level constants before first def)
        first_def_lineno = None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                first_def_lineno = node.lineno
                break

        if first_def_lineno is not None and first_def_lineno > 1:
            preamble_lines = lines[: first_def_lineno - 1]
            preamble_text = "\n".join(preamble_lines).strip()
            if preamble_text:
                chunks.append(
                    CodeChunk(
                        id=f"{file_path}:1-{first_def_lineno - 1}:module_preamble",
                        file_path=file_path,
                        content=preamble_text,
                        start_line=1,
                        end_line=first_def_lineno - 1,
                        chunk_type=ChunkType.MODULE_PREAMBLE,
                        language="python",
                    )
                )

        # 2. Extract top-level definitions
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = node.end_lineno or start
                chunk_lines = lines[start - 1 : end]
                chunks.append(
                    CodeChunk(
                        id=f"{file_path}:{start}-{end}:{node.name}",
                        file_path=file_path,
                        content="\n".join(chunk_lines),
                        start_line=start,
                        end_line=end,
                        chunk_type=ChunkType.FUNCTION,
                        symbol_name=node.name,
                        language="python",
                    )
                )

            elif isinstance(node, ast.ClassDef):
                start = node.lineno
                end = node.end_lineno or start

                # Find methods inside class
                methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = [
                    item
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]

                # If class has methods, chunk class declaration/docstring and each method
                if methods:
                    first_method_line = methods[0].lineno
                    class_header_end = max(start, first_method_line - 1)
                    class_header = "\n".join(lines[start - 1 : class_header_end]).strip()

                    chunks.append(
                        CodeChunk(
                            id=f"{file_path}:{start}-{class_header_end}:{node.name}",
                            file_path=file_path,
                            content=class_header,
                            start_line=start,
                            end_line=class_header_end,
                            chunk_type=ChunkType.CLASS,
                            symbol_name=node.name,
                            language="python",
                        )
                    )

                    for method in methods:
                        m_start = method.lineno
                        m_end = method.end_lineno or m_start
                        m_lines = lines[m_start - 1 : m_end]
                        chunks.append(
                            CodeChunk(
                                id=f"{file_path}:{m_start}-{m_end}:{node.name}.{method.name}",
                                file_path=file_path,
                                content="\n".join(m_lines),
                                start_line=m_start,
                                end_line=m_end,
                                chunk_type=ChunkType.METHOD,
                                symbol_name=method.name,
                                parent_symbol=node.name,
                                language="python",
                            )
                        )
                else:
                    # Class without methods (e.g., pure dataclass or enum)
                    chunks.append(
                        CodeChunk(
                            id=f"{file_path}:{start}-{end}:{node.name}",
                            file_path=file_path,
                            content="\n".join(lines[start - 1 : end]),
                            start_line=start,
                            end_line=end,
                            chunk_type=ChunkType.CLASS,
                            symbol_name=node.name,
                            language="python",
                        )
                    )

        # If no functions or classes were found at all, create a single module chunk
        if not chunks:
            chunks.append(
                CodeChunk(
                    id=f"{file_path}:1-{len(lines)}:module",
                    file_path=file_path,
                    content=content,
                    start_line=1,
                    end_line=len(lines),
                    chunk_type=ChunkType.MODULE_PREAMBLE,
                    language="python",
                )
            )

        return chunks
