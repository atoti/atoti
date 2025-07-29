#!/usr/bin/env python3
"""
Advanced Document Processing and Q&A System with LangGraph

This system combines document indexing and question-answering using LangGraph's
state management and workflow capabilities.

MAJOR IMPROVEMENTS OVER SIMPLE SCRIPT:
- State-driven processing with error recovery
- Quality validation at each step
- Modular, reusable components
- Comprehensive error handling
- Progress tracking and observability
- Retry mechanisms for failed operations

Integrated functionality from index_docs.py:
- Web crawling and document loading
- HTML content cleaning with BeautifulSoup
- Content filtering and quality assessment
- Text chunking with optimal parameters
- Vector database creation with Chroma
- Embedding generation with Ollama
"""

from typing import TypedDict, Literal, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain.prompts import ChatPromptTemplate
from langchain.schema.output_parser import StrOutputParser
from langchain.schema import Document
from langchain_community.document_loaders import RecursiveUrlLoader
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from bs4 import BeautifulSoup
import asyncio
import os
import shutil
import re
from datetime import datetime


# 1. DEFINE COMPREHENSIVE STATE FOR DOCUMENT PROCESSING AND Q&A
class DocumentProcessingState(TypedDict):
    """Enhanced state that tracks the entire document processing and Q&A workflow."""

    # Document Processing State
    source_url: str
    raw_documents: List[Document]
    cleaned_documents: List[Document]
    document_chunks: List[Document]
    embeddings_model: str
    vectordb_path: str
    processing_stats: Dict[str, Any]

    # Q&A State
    user_question: str
    retrieved_docs: List[Document]
    context: str
    response: str
    confidence: float

    # Workflow State
    current_step: str
    step_count: int
    retry_count: int
    error_message: str
    processing_log: List[str]

    # Quality Metrics
    document_quality_score: float
    response_quality_score: float
    validation_passed: bool


class AdvancedAtotiQASystem:
    """
    Advanced document processing and Q&A system using LangGraph.

    INTEGRATED FUNCTIONALITY FROM index_docs.py:
    - Web crawling with RecursiveUrlLoader
    - HTML cleaning with BeautifulSoup
    - Content quality filtering
    - Text chunking with RecursiveCharacterTextSplitter
    - Vector database creation with Chroma
    - Ollama embeddings integration

    NEW LANGGRAPH ENHANCEMENTS:
    - State-driven workflow with error recovery
    - Quality validation at each step
    - Retry mechanisms for failed operations
    - Progress tracking and observability
    - Modular, reusable processing steps
    """

    def __init__(self):
        self.llm = None
        self.graph = None
        self.qa_graph = None  # Separate graph for Q&A only
        self.embeddings = None

    def setup(self):
        """Initialize the LLM, embeddings, and build the processing graph."""
        print("🔧 Setting up Advanced Atoti Document Processing & Q&A System...")

        # Initialize LLM (using Ollama)
        self.llm = ChatOllama(
            model="mistral:latest",
            temperature=0.1,  # Lower temperature for more consistent responses
        )

        # Initialize embeddings
        try:
            self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
            print("✅ Ollama embeddings initialized")
        except Exception as e:
            print(f"❌ Failed to initialize embeddings: {e}")
            return False

        # Build the comprehensive processing graph
        self.graph = self._build_document_processing_graph()

        # Build the separate Q&A-only graph
        self.qa_graph = self._build_qa_only_graph()

        print("✅ Advanced system setup complete!")
        return True

    def _build_document_processing_graph(self):
        """
        Build the comprehensive LangGraph workflow that integrates all functionality
        from index_docs.py into a state-driven, error-resilient system.

        WORKFLOW STEPS:
        1. Initialize → Set up processing parameters
        2. Load Documents → Web crawling with RecursiveUrlLoader
        3. Clean HTML → BeautifulSoup content cleaning
        4. Filter Content → Quality assessment and filtering
        5. Chunk Documents → Text splitting with optimal parameters
        6. Create Embeddings → Generate vector representations
        7. Build Vector DB → Create and persist Chroma database
        8. Validate DB → Quality checks and validation
        9. Q&A Ready → System ready for questions
        """
        # Create the graph
        workflow = StateGraph(DocumentProcessingState)

        # DOCUMENT PROCESSING NODES
        workflow.add_node("initialize", self._initialize_processing)
        workflow.add_node("load_documents", self._load_documents)
        workflow.add_node("clean_html", self._clean_html_content)
        workflow.add_node("filter_content", self._filter_content_quality)
        workflow.add_node("chunk_documents", self._chunk_documents)
        workflow.add_node("create_embeddings", self._create_embeddings)
        workflow.add_node("build_vectordb", self._build_vector_database)
        workflow.add_node("validate_db", self._validate_database)

        # Q&A PROCESSING NODES
        workflow.add_node("retrieve_docs", self._retrieve_relevant_docs)
        workflow.add_node("generate_answer", self._generate_answer)
        workflow.add_node("validate_answer", self._validate_answer)

        # ENTRY POINTS
        workflow.set_entry_point("initialize")

        # DOCUMENT PROCESSING FLOW
        workflow.add_edge("initialize", "load_documents")
        workflow.add_edge("load_documents", "clean_html")
        workflow.add_edge("clean_html", "filter_content")
        workflow.add_edge("filter_content", "chunk_documents")
        workflow.add_edge("chunk_documents", "create_embeddings")
        workflow.add_edge("create_embeddings", "build_vectordb")
        workflow.add_edge("build_vectordb", "validate_db")

        # CONDITIONAL ROUTING AFTER VALIDATION
        workflow.add_conditional_edges(
            "validate_db",
            self._should_retry_processing,
            {
                "retry_load": "load_documents",
                "retry_clean": "clean_html",
                "retry_chunk": "chunk_documents",
                "qa_ready": END,  # End document processing workflow here
            },
        )

        # Q&A FLOW (completely separate from document processing)
        workflow.add_edge("retrieve_docs", "generate_answer")
        workflow.add_edge("generate_answer", "validate_answer")

        # CONDITIONAL ROUTING FOR ANSWER QUALITY
        workflow.add_conditional_edges(
            "validate_answer",
            self._should_retry_answer,
            {"retry": "generate_answer", "finish": END},
        )

        return workflow.compile()

    def _build_qa_only_graph(self):
        """
        Build a separate, lightweight graph just for Q&A that doesn't involve document processing.
        This prevents URL loading errors when asking questions.
        """
        # Create a simple Q&A-only graph
        qa_workflow = StateGraph(DocumentProcessingState)

        # Q&A PROCESSING NODES ONLY
        qa_workflow.add_node("retrieve_docs", self._retrieve_relevant_docs)
        qa_workflow.add_node("generate_answer", self._generate_answer)
        qa_workflow.add_node("validate_answer", self._validate_answer)

        # ENTRY POINT for Q&A
        qa_workflow.set_entry_point("retrieve_docs")

        # Q&A FLOW
        qa_workflow.add_edge("retrieve_docs", "generate_answer")
        qa_workflow.add_edge("generate_answer", "validate_answer")

        # CONDITIONAL ROUTING FOR ANSWER QUALITY
        qa_workflow.add_conditional_edges(
            "validate_answer",
            self._should_retry_answer,
            {"retry": "generate_answer", "finish": END},
        )

        return qa_workflow.compile()

    # 2. DOCUMENT PROCESSING NODES (Integrated from index_docs.py)
    def _initialize_processing(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Initialize the document processing workflow."""
        print("🚀 Initializing document processing...")

        # Set up processing parameters (from index_docs.py configuration)
        source_url = state.get(
            "source_url",
            "https://docs.activeviam.com/products/atoti/python-sdk/0.9.next/",
        )
        vectordb_path = state.get("vectordb_path", "./atoti_docs_vectordb")

        processing_log = ["Processing initialized"]

        return {
            **state,
            "source_url": source_url,
            "vectordb_path": vectordb_path,
            "current_step": "initialize",
            "step_count": 1,
            "retry_count": 0,
            "processing_log": processing_log,
            "processing_stats": {
                "start_time": datetime.now().isoformat(),
                "documents_loaded": 0,
                "documents_cleaned": 0,
                "chunks_created": 0,
            },
        }

    def _load_documents(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Load documents using RecursiveUrlLoader (from index_docs.py)."""
        print("📥 Loading documents from web...")

        processing_log = state.get("processing_log", [])
        processing_log.append("Starting document loading...")
        print(state["source_url"])

        try:
            # Recreate the exact loader configuration from index_docs.py
            loader = RecursiveUrlLoader(
                url=state["source_url"],
                max_depth=4,
                prevent_outside=True,
                use_async=False,
                timeout=60,
                check_response_status=True,
                continue_on_failure=True,
                link_regex=r'<a\s+(?:[^>]*?\s+)?href="([^"]*(?=.html)[^"]*)"',
            )

            documents = loader.load()
            processing_log.append(f"Loaded {len(documents)} raw documents")

            # Update stats
            stats = state.get("processing_stats", {})
            stats["documents_loaded"] = len(documents)

            return {
                **state,
                "raw_documents": documents,
                "current_step": "load_documents",
                "step_count": state["step_count"] + 1,
                "processing_log": processing_log,
                "processing_stats": stats,
            }

        except Exception as e:
            processing_log.append(f"Error loading documents: {str(e)}")
            return {
                **state,
                "error_message": f"Document loading failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "load_documents_error",
            }

    def _clean_html_content(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Clean HTML content using BeautifulSoup (from index_docs.py)."""
        print("🧹 Cleaning HTML content...")

        raw_documents = state.get("raw_documents", [])
        processing_log = state.get("processing_log", [])
        processing_log.append("Starting HTML cleaning...")

        cleaned_documents = []

        try:
            for doc in raw_documents:
                # Skip non-documentation files (from index_docs.py logic)
                url = doc.metadata.get("source", "")
                if any(
                    ext in url
                    for ext in [".css", ".js", ".png", ".jpg", ".ico", ".gif"]
                ):
                    continue

                # Parse HTML and extract clean text (exact logic from index_docs.py)
                soup = BeautifulSoup(doc.page_content, "html.parser")

                # Remove unwanted elements
                for element in soup(
                    ["script", "style", "nav", "footer", "header", "aside", "noscript"]
                ):
                    element.decompose()

                # Remove navigation/UI elements
                for element in soup.find_all(
                    attrs={"class": ["navbar", "sidebar", "breadcrumb", "toc"]}
                ):
                    element.decompose()

                # Focus on main content
                main_content = (
                    soup.find("main")
                    or soup.find("article")
                    or soup.find(attrs={"class": ["content", "main"]})
                )

                text = main_content.get_text() if main_content else soup.get_text()

                # Clean whitespace (from index_docs.py)
                text = re.sub(r"\s+", " ", text).strip()

                # Apply quality filters (adapted from index_docs.py)
                if (
                    len(text) > 500
                    and (
                        "atoti" in text.lower()
                        or "session" in text.lower()
                        or "api" in text.lower()
                    )
                    and not url.endswith("genindex.html")
                    and any(
                        keyword in url.lower()
                        for keyword in ["tutorial", "guide", "api", "changelog"]
                    )
                ):
                    doc.page_content = text
                    cleaned_documents.append(doc)

            processing_log.append(
                f"Cleaned to {len(cleaned_documents)} quality documents"
            )

            # Update stats
            stats = state.get("processing_stats", {})
            stats["documents_cleaned"] = len(cleaned_documents)

            return {
                **state,
                "cleaned_documents": cleaned_documents,
                "current_step": "clean_html",
                "step_count": state["step_count"] + 1,
                "processing_log": processing_log,
                "processing_stats": stats,
            }

        except Exception as e:
            processing_log.append(f"Error cleaning HTML: {str(e)}")
            return {
                **state,
                "error_message": f"HTML cleaning failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "clean_html_error",
            }

    def _filter_content_quality(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Apply additional content quality filtering."""
        print("🔍 Filtering content quality...")

        cleaned_documents = state.get("cleaned_documents", [])
        processing_log = state.get("processing_log", [])

        # Calculate quality score
        total_content = sum(len(doc.page_content) for doc in cleaned_documents)
        avg_content_length = (
            total_content / len(cleaned_documents) if cleaned_documents else 0
        )

        quality_score = min(
            1.0, (len(cleaned_documents) / 100) * (avg_content_length / 1000)
        )

        processing_log.append(f"Content quality score: {quality_score:.2f}")

        return {
            **state,
            "document_quality_score": quality_score,
            "current_step": "filter_content",
            "step_count": state["step_count"] + 1,
            "processing_log": processing_log,
        }

    def _chunk_documents(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Split documents into chunks (from index_docs.py)."""
        print("✂️ Splitting documents into chunks...")

        cleaned_documents = state.get("cleaned_documents", [])
        processing_log = state.get("processing_log", [])
        processing_log.append("Starting document chunking...")

        try:
            # Use exact text splitter configuration from index_docs.py
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1500,
                chunk_overlap=300,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""],
            )

            document_chunks = text_splitter.split_documents(cleaned_documents)
            processing_log.append(
                f"Created {len(document_chunks)} chunks from {len(cleaned_documents)} documents"
            )

            # Update stats
            stats = state.get("processing_stats", {})
            stats["chunks_created"] = len(document_chunks)

            return {
                **state,
                "document_chunks": document_chunks,
                "current_step": "chunk_documents",
                "step_count": state["step_count"] + 1,
                "processing_log": processing_log,
                "processing_stats": stats,
            }

        except Exception as e:
            processing_log.append(f"Error chunking documents: {str(e)}")
            return {
                **state,
                "error_message": f"Document chunking failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "chunk_documents_error",
            }

    def _create_embeddings(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Prepare embeddings for vector database creation."""
        print("🔢 Preparing embeddings...")

        processing_log = state.get("processing_log", [])

        try:
            # Verify embeddings are available
            if not self.embeddings:
                raise Exception("Embeddings not initialized")

            processing_log.append("Embeddings model ready: nomic-embed-text")

            return {
                **state,
                "embeddings_model": "nomic-embed-text",
                "current_step": "create_embeddings",
                "step_count": state["step_count"] + 1,
                "processing_log": processing_log,
            }

        except Exception as e:
            processing_log.append(f"Error with embeddings: {str(e)}")
            return {
                **state,
                "error_message": f"Embeddings preparation failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "create_embeddings_error",
            }

    def _build_vector_database(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Build Chroma vector database (from index_docs.py)."""
        print("🗄️ Building vector database...")

        document_chunks = state.get("document_chunks", [])
        vectordb_path = state["vectordb_path"]
        processing_log = state.get("processing_log", [])
        processing_log.append("Creating Chroma vector database...")

        try:
            # Remove existing database (from index_docs.py)
            if os.path.exists(vectordb_path):
                shutil.rmtree(vectordb_path)
                processing_log.append(f"Removed existing database at {vectordb_path}")

            # Create new vector database (exact logic from index_docs.py)
            Chroma.from_documents(
                documents=document_chunks,
                embedding=self.embeddings,
                persist_directory=vectordb_path,
            )

            processing_log.append(
                f"Successfully created vector database with {len(document_chunks)} chunks"
            )
            processing_log.append(f"Database persisted to: {vectordb_path}")

            return {
                **state,
                "current_step": "build_vectordb",
                "step_count": state["step_count"] + 1,
                "processing_log": processing_log,
            }

        except Exception as e:
            processing_log.append(f"Error building vector database: {str(e)}")
            return {
                **state,
                "error_message": f"Vector database creation failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "build_vectordb_error",
            }

    def _validate_database(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Validate the created vector database."""
        print("✅ Validating vector database...")

        vectordb_path = state["vectordb_path"]
        processing_log = state.get("processing_log", [])

        try:
            # Check if database exists and is accessible
            if os.path.exists(vectordb_path):
                # Try to load the database
                vectordb = Chroma(
                    persist_directory=vectordb_path, embedding_function=self.embeddings
                )

                # Test a simple query
                test_results = vectordb.similarity_search("atoti session", k=1)

                validation_passed = len(test_results) > 0
                processing_log.append(
                    f"Database validation: {'PASSED' if validation_passed else 'FAILED'}"
                )

                return {
                    **state,
                    "validation_passed": validation_passed,
                    "current_step": "validate_db",
                    "step_count": state["step_count"] + 1,
                    "processing_log": processing_log,
                }
            else:
                processing_log.append("Database validation FAILED: Database not found")
                return {
                    **state,
                    "validation_passed": False,
                    "error_message": "Database not found",
                    "processing_log": processing_log,
                    "current_step": "validate_db_error",
                }

        except Exception as e:
            processing_log.append(f"Database validation error: {str(e)}")
            return {
                **state,
                "validation_passed": False,
                "error_message": f"Database validation failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "validate_db_error",
            }

    # 3. Q&A PROCESSING NODES
    def _retrieve_relevant_docs(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Retrieve relevant documents for Q&A."""
        user_question = state.get("user_question", "")
        if not user_question:
            return {**state, "current_step": "qa_ready"}

        print(f"🔍 Retrieving documents for: {user_question}")

        vectordb_path = state["vectordb_path"]
        processing_log = state.get("processing_log", [])

        try:
            # Load the vector database
            vectordb = Chroma(
                persist_directory=vectordb_path, embedding_function=self.embeddings
            )

            # Retrieve relevant documents
            retrieved_docs = vectordb.similarity_search(user_question, k=6)
            processing_log.append(f"Retrieved {len(retrieved_docs)} relevant documents")

            return {
                **state,
                "retrieved_docs": retrieved_docs,
                "current_step": "retrieve_docs",
                "step_count": state["step_count"] + 1,
                "processing_log": processing_log,
            }

        except Exception as e:
            processing_log.append(f"Error retrieving documents: {str(e)}")
            return {
                **state,
                "error_message": f"Document retrieval failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "retrieve_docs_error",
            }

    def _generate_answer(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Generate answer using retrieved documents."""
        print("🤖 Generating answer...")

        user_question = state["user_question"]
        retrieved_docs = state.get("retrieved_docs", [])
        processing_log = state.get("processing_log", [])

        try:
            # Format context from retrieved documents
            context_parts = []
            for i, doc in enumerate(retrieved_docs, 1):
                source = doc.metadata.get("source", "Unknown")
                content = doc.page_content.strip()
                context_parts.append(
                    f"=== DOCUMENT {i} ===\nSource: {source}\nContent: {content}\n"
                )

            context = "\n".join(context_parts)

            # Create prompt for Atoti-specific Q&A
            template = """You are an expert assistant for the Atoti Python SDK documentation.

INSTRUCTIONS:
- ONLY answer questions about Atoti Python SDK
- ONLY use information explicitly stated in the provided context
- If the context doesn't contain relevant information, say "I don't have information about this topic in the Atoti documentation provided."
- Be precise and cite specific methods, classes, or examples from the context

CONTEXT FROM ATOTI DOCUMENTATION:
{context}

QUESTION: {question}

ANSWER (based only on the provided context):"""

            prompt = ChatPromptTemplate.from_template(template)
            chain = prompt | self.llm | StrOutputParser()

            response = chain.invoke({"context": context, "question": user_question})

            processing_log.append("Answer generated successfully")

            return {
                **state,
                "context": context,
                "response": response,
                "current_step": "generate_answer",
                "step_count": state["step_count"] + 1,
                "processing_log": processing_log,
            }

        except Exception as e:
            processing_log.append(f"Error generating answer: {str(e)}")
            return {
                **state,
                "error_message": f"Answer generation failed: {str(e)}",
                "processing_log": processing_log,
                "current_step": "generate_answer_error",
            }

    def _validate_answer(
        self, state: DocumentProcessingState
    ) -> DocumentProcessingState:
        """Validate the generated answer quality."""
        print("✅ Validating answer quality...")

        response = state.get("response", "")
        user_question = state["user_question"]
        processing_log = state.get("processing_log", [])

        # Calculate response quality score
        quality_score = 0.5  # Base score

        # Check response length
        if len(response) > 50:
            quality_score += 0.2

        # Check if it addresses the question
        question_words = set(user_question.lower().split())
        response_words = set(response.lower().split())
        relevance = (
            len(question_words.intersection(response_words)) / len(question_words)
            if question_words
            else 0
        )
        quality_score += relevance * 0.3

        # Check for Atoti-specific content
        if any(
            term in response.lower() for term in ["atoti", "session", "cube", "measure"]
        ):
            quality_score += 0.2

        quality_score = min(1.0, quality_score)

        processing_log.append(f"Response quality score: {quality_score:.2f}")

        return {
            **state,
            "response_quality_score": quality_score,
            "current_step": "validate_answer",
            "step_count": state["step_count"] + 1,
            "processing_log": processing_log,
        }

    # 4. CONDITIONAL ROUTING LOGIC
    def _should_retry_processing(
        self, state: DocumentProcessingState
    ) -> Literal["retry_load", "retry_clean", "retry_chunk", "qa_ready"]:
        """Determine if document processing should be retried."""
        validation_passed = state.get("validation_passed", False)
        retry_count = state.get("retry_count", 0)
        current_step = state.get("current_step", "")

        if validation_passed:
            print("✅ Document processing completed successfully")
            return "qa_ready"

        if retry_count >= 2:
            print("❌ Maximum retries reached, proceeding anyway")
            return "qa_ready"

        # Determine retry strategy based on where the error occurred
        if "load" in current_step and retry_count < 2:
            print("🔄 Retrying document loading...")
            return "retry_load"
        elif "clean" in current_step and retry_count < 2:
            print("🔄 Retrying HTML cleaning...")
            return "retry_clean"
        elif "chunk" in current_step and retry_count < 2:
            print("🔄 Retrying document chunking...")
            return "retry_chunk"
        else:
            return "qa_ready"

    def _should_retry_answer(
        self, state: DocumentProcessingState
    ) -> Literal["retry", "finish"]:
        """Determine if answer generation should be retried."""
        quality_score = state.get("response_quality_score", 0)
        retry_count = state.get("retry_count", 0)

        if quality_score >= 0.7:
            print("✅ High quality answer generated")
            return "finish"

        if retry_count >= 1:
            print("📝 Accepting answer after retry")
            return "finish"

        print("🔄 Retrying answer generation for better quality...")
        return "retry"

    # 5. MAIN INTERFACES
    async def process_documents(
        self, source_url: str = None, vectordb_path: str = None
    ) -> dict:
        """Process documents and create vector database."""
        print("🚀 Starting comprehensive document processing...")

        initial_state = {
            "source_url": source_url
            or "https://docs.activeviam.com/products/atoti/python-sdk/0.9.next/",
            "vectordb_path": vectordb_path or "./atoti_docs_vectordb",
            "raw_documents": [],
            "cleaned_documents": [],
            "document_chunks": [],
            "embeddings_model": "",
            "processing_stats": {},
            "user_question": "",  # No question for processing mode
            "retrieved_docs": [],
            "context": "",
            "response": "",
            "confidence": 0.0,
            "current_step": "",
            "step_count": 0,
            "retry_count": 0,
            "error_message": "",
            "processing_log": [],
            "document_quality_score": 0.0,
            "response_quality_score": 0.0,
            "validation_passed": False,
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)
            self._display_processing_results(final_state)
            return final_state
        except Exception as e:
            print(f"❌ Error in document processing: {e}")
            return {"error": str(e)}

    async def ask_question(self, question: str, vectordb_path: str = None) -> dict:
        """Ask a question using the processed documents."""
        print(f"❓ Question: {question}")

        # Create state for Q&A mode (skip document processing)
        qa_state = {
            "source_url": "",
            "vectordb_path": vectordb_path or "./atoti_docs_vectordb",
            "raw_documents": [],
            "cleaned_documents": [],
            "document_chunks": [],
            "embeddings_model": "nomic-embed-text",
            "processing_stats": {},
            "user_question": question,
            "retrieved_docs": [],
            "context": "",
            "response": "",
            "confidence": 0.0,
            "current_step": "qa_ready",
            "step_count": 0,
            "retry_count": 0,
            "error_message": "",
            "processing_log": ["Starting Q&A mode"],
            "document_quality_score": 1.0,
            "response_quality_score": 0.0,
            "validation_passed": True,
        }

        try:
            # Use the separate Q&A graph that doesn't involve document processing
            final_state = await self.qa_graph.ainvoke(qa_state)
            self._display_qa_results(final_state)
            return final_state
        except Exception as e:
            print(f"❌ Error in Q&A processing: {e}")
            return {"error": str(e)}

    def _display_processing_results(self, state: dict):
        """Display document processing results."""
        processing_log = state.get("processing_log", [])
        stats = state.get("processing_stats", {})

        print("\n" + "=" * 70)
        print("📊 DOCUMENT PROCESSING COMPLETED")
        print("=" * 70)

        print("📈 Processing Statistics:")
        print(f"  • Documents loaded: {stats.get('documents_loaded', 0)}")
        print(f"  • Documents cleaned: {stats.get('documents_cleaned', 0)}")
        print(f"  • Chunks created: {stats.get('chunks_created', 0)}")
        print(f"  • Quality score: {state.get('document_quality_score', 0):.2f}")
        print(f"  • Steps completed: {state.get('step_count', 0)}")

        print("\n📝 Processing Log:")
        for i, log_entry in enumerate(processing_log, 1):
            print(f"  {i}. {log_entry}")

        if state.get("validation_passed"):
            print("\n✅ Vector database ready for Q&A!")
        else:
            print("\n⚠️ Processing completed with issues")

        print("=" * 70)

    def _display_qa_results(self, state: dict):
        """Display Q&A results."""
        response = state.get("response", "No response generated")
        quality_score = state.get("response_quality_score", 0)
        retrieved_docs = state.get("retrieved_docs", [])

        print("\n" + "=" * 70)
        print("💡 ANSWER")
        print("=" * 70)
        print(response)

        print(f"\n📊 Quality Score: {quality_score:.1%}")
        print(f"📚 Sources Used: {len(retrieved_docs)} documents")

        if quality_score < 0.5:
            print("⚠️ Low quality score - please verify the information")
        elif quality_score < 0.7:
            print("🔍 Moderate quality - cross-reference recommended")
        else:
            print("✅ High quality answer")

        print("=" * 70)


# 5. USAGE EXAMPLES
async def example_document_processing():
    """Example of how to use document processing."""
    print("🔬 Running Document Processing Example")
    print("=" * 50)

    # Initialize the system
    qa_system = AdvancedAtotiQASystem()
    qa_system.setup()

    # Process documents from Atoti documentation
    print("📚 Processing Atoti documentation...")
    result = await qa_system.process_documents()

    if "error" not in result:
        print("✅ Document processing completed successfully!")
        return result
    else:
        print(f"❌ Processing failed: {result['error']}")
        return None


async def example_qa_session():
    """Example of how to ask questions."""
    print("\n🤖 Running Q&A Example")
    print("=" * 50)

    # Initialize the system
    qa_system = AdvancedAtotiQASystem()
    qa_system.setup()

    # Example questions about Atoti
    questions = [
        "How do I create a session in Atoti?",
        "What is a cube in Atoti?",
        "How do I add measures to a cube?",
    ]

    for question in questions:
        result = await qa_system.ask_question(question)
        if "error" not in result:
            print(f"✅ Successfully answered: {question}")
        else:
            print(f"❌ Failed to answer: {question}")
        print("-" * 30)


async def main():
    """Main function demonstrating the Atoti Q&A system."""
    print("🚀 Advanced Atoti Q&A System with LangGraph")
    print("=" * 60)

    # Run document processing example
    await example_document_processing()

    # Run Q&A example
    await example_qa_session()

    print("\n🎉 Examples completed!")


# 6. INTERACTIVE MODE
async def interactive_mode():
    """Run in interactive Q&A mode."""
    print("🎯 Interactive Atoti Q&A System")
    print("Type 'quit' to exit")
    print("-" * 30)

    qa_system = AdvancedAtotiQASystem()
    qa_system.setup()

    # Check if vector database exists
    import os

    if not os.path.exists("./atoti_docs_vectordb"):
        print("📚 Vector database not found. Processing documents first...")
        await qa_system.process_documents()

    while True:
        try:
            question = input("\n❓ Ask about Atoti: ").strip()

            if not question:
                continue

            if question.lower() in ["quit", "exit", "q"]:
                print("👋 Goodbye!")
                break

            await qa_system.ask_question(question)

        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except EOFError:
            print("\n👋 Goodbye!")
            break


if __name__ == "__main__":
    import sys
    import asyncio

    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        # Interactive mode
        asyncio.run(interactive_mode())
    else:
        # Demo mode
        asyncio.run(main())
