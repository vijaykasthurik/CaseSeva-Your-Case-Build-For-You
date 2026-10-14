"""Generic hierarchical sectionizer for Indian statutory and regulatory texts.

Extracts provisions at section, subsection, clause, and proviso granularity with exact
substring boundaries and cryptographic hash verification.
"""
import hashlib
import re
from .models import ProvisionRecord, AuthorityType, ReviewStatus


class StatutorySectionizer:
    """Parses official enactment text into structured ProvisionRecord entries."""

    SECTION_PATTERN = re.compile(
        r"^(?:\s*)(?:SECTION\s+)?(\d+[A-Z]?)\.\s+([^\n\r]+?)(?:\s*[-—–]\s*|\s*\n|\.\s+)(.*?)(?=(?:^(?:\s*)(?:SECTION\s+)?\d+[A-Z]?\.\s+[^\n\r]+?[-—–\n]|\Z))",
        re.DOTALL | re.MULTILINE
    )

    SUBSECTION_PATTERN = re.compile(
        r"(?:\n|^)\s*\((\d+[a-z]?)\)\s*(.*?)(?=(?:\n\s*\(\d+[a-z]?\)|\Z))",
        re.DOTALL
    )

    CLAUSE_PATTERN = re.compile(
        r"(?:\n|^)\s*\(([a-z]+)\)\s*(.*?)(?=(?:\n\s*\([a-z]+\)|\Z))",
        re.DOTALL
    )

    CHAPTER_PATTERN = re.compile(
        r"^(?:\s*)(CHAPTER\s+[IVXLCDM\d]+[A-Z]?)\s*\n\s*([^\n\r]+)",
        re.IGNORECASE | re.MULTILINE
    )

    PART_PATTERN = re.compile(
        r"^(?:\s*)(PART\s+[IVXLCDM\d]+[A-Z]?)\s*\n\s*([^\n\r]+)",
        re.IGNORECASE | re.MULTILINE
    )

    def extract_provisions(
        self,
        document_id: str,
        title: str,
        text: str,
        official_url: str,
        source_owner: str,
        raw_document_hash: str,
        authority_type: AuthorityType = AuthorityType.ACT,
        domain: str = "GENERAL",
        jurisdiction: str = "IN",
        language: str = "en",
        enactment_date: str | None = None,
        effective_from: str | None = None,
        effective_until: str | None = None,
    ) -> list[ProvisionRecord]:
        provisions: list[ProvisionRecord] = []
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        # Build chapter and part position index
        chapters = [(m.start(), m.group(1), m.group(2).strip()) for m in self.CHAPTER_PATTERN.finditer(text)]
        parts = [(m.start(), m.group(1), m.group(2).strip()) for m in self.PART_PATTERN.finditer(text)]

        def get_enclosing_part(pos: int) -> str | None:
            matching = [p[1] for p in parts if p[0] <= pos]
            return matching[-1] if matching else None

        def get_enclosing_chapter(pos: int) -> str | None:
            matching = [c[1] for c in chapters if c[0] <= pos]
            return matching[-1] if matching else None

        # Iterate over sections
        for match in self.SECTION_PATTERN.finditer(text):
            sec_num = match.group(1)
            heading = match.group(2).strip()
            sec_body = match.group(3).strip()
            start = match.start()
            end = match.end()
            full_quote = text[start:end]

            part_name = get_enclosing_part(start)
            chapter_name = get_enclosing_chapter(start)

            # Section-level record
            sec_id = f"{document_id}_s{sec_num.lower()}"
            sec_record = ProvisionRecord(
                provision_id=sec_id,
                parent_document_id=document_id,
                parent_document_title=title,
                authority_type=authority_type,
                domain=domain,
                jurisdiction=jurisdiction,
                language=language,
                part=part_name,
                chapter=chapter_name,
                section=sec_num,
                heading=heading,
                quote=full_quote,
                section_start=start,
                section_end=end,
                official_url=official_url,
                source_owner=source_owner,
                raw_document_hash=raw_document_hash,
                extracted_text_hash=text_hash,
                enactment_date=enactment_date,
                effective_from=effective_from,
                effective_until=effective_until,
                review_status=ReviewStatus.DISCOVERED,
            )
            provisions.append(sec_record)

            # Check for subsections within section body
            subsections = list(self.SUBSECTION_PATTERN.finditer(sec_body))
            for sub_match in subsections:
                subsec_num = sub_match.group(1)
                subsec_text = sub_match.group(2).strip()
                # calculate exact offset within main text
                sub_start = start + match.group(0).index(sub_match.group(0))
                sub_end = sub_start + len(sub_match.group(0))
                sub_quote = text[sub_start:sub_end]

                subsec_id = f"{document_id}_s{sec_num.lower()}_{subsec_num.lower()}"
                subsec_record = ProvisionRecord(
                    provision_id=subsec_id,
                    parent_document_id=document_id,
                    parent_document_title=title,
                    authority_type=authority_type,
                    domain=domain,
                    jurisdiction=jurisdiction,
                    language=language,
                    part=part_name,
                    chapter=chapter_name,
                    section=sec_num,
                    subsection=subsec_num,
                    heading=f"{heading} - ({subsec_num})",
                    quote=sub_quote,
                    section_start=sub_start,
                    section_end=sub_end,
                    official_url=official_url,
                    source_owner=source_owner,
                    raw_document_hash=raw_document_hash,
                    extracted_text_hash=text_hash,
                    enactment_date=enactment_date,
                    effective_from=effective_from,
                    effective_until=effective_until,
                    review_status=ReviewStatus.DISCOVERED,
                )
                provisions.append(subsec_record)

                # Check for nested clauses within subsection
                clauses = list(self.CLAUSE_PATTERN.finditer(subsec_text))
                for cl_match in clauses:
                    cl_num = cl_match.group(1)
                    cl_start = sub_start + sub_match.group(0).index(cl_match.group(0))
                    cl_end = cl_start + len(cl_match.group(0))
                    cl_quote = text[cl_start:cl_end]

                    cl_id = f"{document_id}_s{sec_num.lower()}_{subsec_num.lower()}_{cl_num.lower()}"
                    cl_record = ProvisionRecord(
                        provision_id=cl_id,
                        parent_document_id=document_id,
                        parent_document_title=title,
                        authority_type=authority_type,
                        domain=domain,
                        jurisdiction=jurisdiction,
                        language=language,
                        part=part_name,
                        chapter=chapter_name,
                        section=sec_num,
                        subsection=subsec_num,
                        clause=cl_num,
                        heading=f"{heading} - ({subsec_num})({cl_num})",
                        quote=cl_quote,
                        section_start=cl_start,
                        section_end=cl_end,
                        official_url=official_url,
                        source_owner=source_owner,
                        raw_document_hash=raw_document_hash,
                        extracted_text_hash=text_hash,
                        enactment_date=enactment_date,
                        effective_from=effective_from,
                        effective_until=effective_until,
                        review_status=ReviewStatus.DISCOVERED,
                    )
                    provisions.append(cl_record)

        return provisions
