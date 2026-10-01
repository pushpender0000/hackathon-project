"""
Local RAG tool using ChromaDB and local ONNX/SentenceTransformer embeddings.

Grounded entirely in synthetic benchmark chargeback rules without external API calls.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import chromadb
from src.config.settings import get_settings


class PolicyRAGRetriever:
    """Local vector store for synthetic chargeback rules."""

    def __init__(self):
        settings = get_settings()
        self.rules_file: Path = settings.policy_corpus_dir / "synthetic_chargeback_rules.json"
        self._client = chromadb.Client()
        self._collection = self._client.get_or_create_collection(name="synthetic_policy_rules")
        self._initialize_index()

    def _initialize_index(self):
        """Indexes the 4 synthetic benchmark rules into the ChromaDB collection."""
        if not self.rules_file.exists():
            return

        with open(self.rules_file, "r", encoding="utf-8") as f:
            rules: List[Dict[str, Any]] = json.load(f)

        existing = self._collection.get()
        if existing and existing["ids"]:
            return  # Already populated

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for rule in rules:
            ids.append(rule["rule_id"])
            doc_text = (
                f"Rule ID: {rule['rule_id']}\n"
                f"Title: {rule['title']}\n"
                f"Category: {rule['category']}\n"
                f"Description: {rule['description']}\n"
                f"Section: {rule['synthetic_section']}\n"
                f"Evidence: {', '.join(rule['required_evidence'])}"
            )
            documents.append(doc_text)
            metadatas.append({
                "rule_id": rule["rule_id"],
                "category": rule["category"],
                "title": rule["title"],
                "max_filing_days": rule["max_filing_days"],
                "synthetic_section": rule["synthetic_section"],
                "required_evidence": json.dumps(rule["required_evidence"]),
            })

        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def retrieve_best_rule(
        self,
        query_text: str,
        candidate_rule_ids: Optional[List[str]] = None,
        min_confidence_score: Optional[float] = None,
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """
        Retrieves the best matching synthetic rule from ChromaDB.

        Returns:
            Tuple of (rule_metadata_dict, confidence_score) or None if retrieval fails.
        """
        settings = get_settings()
        threshold = min_confidence_score if min_confidence_score is not None else settings.rag_retrieval_threshold

        where_filter = None
        if candidate_rule_ids:
            if len(candidate_rule_ids) == 1:
                where_filter = {"rule_id": candidate_rule_ids[0]}
            else:
                where_filter = {"rule_id": {"$in": candidate_rule_ids}}

        results = self._collection.query(
            query_texts=[query_text],
            n_results=1,
            where=where_filter,
        )

        if not results or not results["ids"] or not results["ids"][0]:
            return None

        rule_id = results["ids"][0][0]
        metadata = results["metadatas"][0][0]
        distance = results["distances"][0][0] if results.get("distances") else 0.5
        
        # Approximate similarity score = 1 / (1 + distance)
        confidence_score = round(1.0 / (1.0 + float(distance)), 3)

        if confidence_score < threshold:
            return None

        # Unpack evidence list from json string
        evidence_list = json.loads(metadata.get("required_evidence", "[]"))

        rule_data = {
            "rule_id": metadata["rule_id"],
            "title": metadata["title"],
            "category": metadata["category"],
            "max_filing_days": int(metadata["max_filing_days"]),
            "synthetic_section": metadata["synthetic_section"],
            "required_evidence": evidence_list,
        }

        return rule_data, confidence_score


_rag_retriever_instance: Optional[PolicyRAGRetriever] = None


def get_rag_retriever() -> PolicyRAGRetriever:
    global _rag_retriever_instance
    if _rag_retriever_instance is None:
        _rag_retriever_instance = PolicyRAGRetriever()
    return _rag_retriever_instance
