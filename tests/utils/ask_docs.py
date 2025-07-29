#!/usr/bin/env python3
"""
Question-Answering system for Atoti documentation using Ollama and Chroma vector database.

This script loads the previously created vector database and uses Mistral-7B via Ollama
to answer questions about the Atoti documentation.

Requirements:
- Ollama installed with mistral:7b model pulled
- Vector database created by index_docs.py
- Required packages: langchain-chroma, langchain-ollama
"""

from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnablePassthrough
from langchain.schema.output_parser import StrOutputParser
import os
import sys


def load_vector_database():
    """Load the existing Chroma vector database."""
    persist_directory = "./atoti_docs_vectordb"

    if not os.path.exists(persist_directory):
        print(f"❌ Vector database not found at {persist_directory}")
        print("Please run index_docs.py first to create the database.")
        sys.exit(1)

    print("🔄 Loading vector database...")

    # Initialize the same embeddings used during indexing
    try:
        import ollama

        result = ollama.list()

        # Extract model names properly
        if hasattr(result, "get") and "models" in result:
            models = result["models"]
        elif hasattr(result, "__iter__"):
            models = list(result)
        else:
            models = []

        model_names = []
        for model in models:
            if hasattr(model, "get") and "model" in model:
                model_names.append(model["model"])
            elif hasattr(model, "model"):
                model_names.append(model.model)
            else:
                model_names.append(str(model))

        if any("nomic-embed-text" in name for name in model_names):
            embeddings = OllamaEmbeddings(model="nomic-embed-text")
            print("✅ Using Ollama embeddings with nomic-embed-text model")
        else:
            print("❌ nomic-embed-text model not found in Ollama")
            print("Please run: ollama pull nomic-embed-text")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Failed to initialize Ollama embeddings: {e}")
        sys.exit(1)

    # Load the vector database
    vectordb = Chroma(
        persist_directory=persist_directory, embedding_function=embeddings
    )

    print("✅ Vector database loaded successfully")
    return vectordb


def initialize_mistral():
    """Initialize Mistral-7B model via Ollama."""
    print("🔄 Initializing Mistral-7B model...")

    try:
        import ollama

        result = ollama.list()

        # Extract model names properly
        if hasattr(result, "get") and "models" in result:
            models = result["models"]
        elif hasattr(result, "__iter__"):
            models = list(result)
        else:
            models = []

        model_names = []
        for model in models:
            if hasattr(model, "get") and "model" in model:
                model_names.append(model["model"])
            elif hasattr(model, "model"):
                model_names.append(model.model)
            else:
                model_names.append(str(model))

        # Check for various Mistral model names
        mistral_models = [name for name in model_names if "mistral" in name.lower()]

        if not mistral_models:
            print("❌ No Mistral model found in Ollama")
            print("Please run one of:")
            print("  ollama pull mistral:7b")
            print("  ollama pull mistral")
            print("  ollama pull mistral:latest")
            sys.exit(1)

        # Use the first available Mistral model
        chosen_model = mistral_models[0]
        print(f"✅ Using Mistral model: {chosen_model}")

        llm = ChatOllama(
            model=chosen_model,
            temperature=0.0,  # Zero temperature for maximum consistency
            num_ctx=8192,  # Larger context window for more information
            num_predict=800,  # Moderate response length to avoid rambling
            top_p=0.9,  # Nucleus sampling for more focused responses
            repeat_penalty=1.1,  # Slight penalty to avoid repetition
        )

        return llm, chosen_model

    except Exception as e:
        print(f"❌ Failed to initialize Mistral: {e}")
        sys.exit(1)


def create_rag_chain(vectordb, llm):
    """Create a RAG (Retrieval-Augmented Generation) chain with improved settings."""

    # Create a retriever with similarity search (more reliable than MMR for accuracy)
    retriever = vectordb.as_retriever(
        search_type="similarity",  # More reliable than MMR for factual accuracy
        search_kwargs={
            "k": 6  # Moderate number of chunks for good context
        },
    )

    # Enhanced prompt template for better responses
    template = """You are an expert assistant for the Atoti Python SDK documentation.

CRITICAL INSTRUCTIONS:
- ONLY answer questions about the Atoti Python SDK
- ONLY use information that is explicitly stated in the provided context
- DO NOT provide general programming advice or information about non-Atoti topics
- If the question is not about Atoti or the context doesn't contain relevant information, respond with: "I don't have information about this topic in the Atoti documentation provided."
- DO NOT make assumptions, inferences, or add external knowledge
- Be direct and factual, citing specific methods, classes, or examples from the context

CONTEXT FROM ATOTI DOCUMENTATION:
{context}

QUESTION: {question}

ACCURATE ANSWER (based only on the provided context):"""

    prompt = ChatPromptTemplate.from_template(template)

    # Create the RAG chain
    def format_docs(docs):
        if not docs:
            return "No relevant documentation found."

        formatted = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "Unknown source")
            content = doc.page_content.strip()

            # Extract meaningful title from URL
            title = source.split("/")[-1].replace(".html", "").replace("_", " ").title()

            formatted.append(
                f"--- DOCUMENT {i}: {title} ---\nSource: {source}\nContent: {content}\n"
            )

        return "\n".join(formatted)

    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    return rag_chain, retriever


def validate_response(answer, docs, question):
    """Basic validation to check if response is grounded in context."""
    if not answer or not docs:
        return False, "No answer or context provided"

    # Check for common hallucination patterns
    hallucination_indicators = [
        "I don't see this in the documentation",
        "Based on general knowledge",
        "Typically in Python",
        "Usually you would",
        "In most cases",
        "Generally speaking",
    ]

    for indicator in hallucination_indicators:
        if indicator.lower() in answer.lower():
            return False, f"Potential hallucination detected: {indicator}"

    # Check if answer contains information not in context
    answer_lower = answer.lower()
    context_text = " ".join([doc.page_content.lower() for doc in docs])

    # Look for specific technical terms that might be hallucinated
    technical_terms = ["import", "def ", "class ", "atoti.", "session."]
    for term in technical_terms:
        if term in answer_lower and term not in context_text:
            return False, f"Technical detail '{term}' not found in context"

    return True, "Response appears grounded in context"


def ask_question(rag_chain, retriever, question):
    """Ask a question and get an answer with sources."""
    print(f"\n🤔 Question: {question}")
    print("🔍 Searching documentation...")

    # Get relevant documents first
    docs = retriever.invoke(question)

    if not docs:
        print("❌ No relevant documents found for this question.")
        print(
            "💡 Try rephrasing your question or check if the topic is covered in the documentation."
        )
        return None

    print(f"📚 Found {len(docs)} relevant document chunks")

    # Show what documents we're using for transparency
    print("🔎 Using sources:")
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "Unknown")
        title = source.split("/")[-1].replace(".html", "").replace("_", " ").title()
        print(f"  {i}. {title} ({len(doc.page_content)} chars)")

    # Generate answer
    print("🤖 Generating answer with Mistral...")
    try:
        answer = rag_chain.invoke(question)

        # Validate response for hallucinations
        is_valid, validation_msg = validate_response(answer, docs, question)

        if not is_valid:
            print(f"⚠️  Warning: {validation_msg}")
            print(
                "🔄 This response may contain inaccurate information. Please verify against the source documents."
            )

        print("\n✅ Answer:")
        print("-" * 60)
        print(answer)
        print("-" * 60)

        # Show sources
        print("\n📖 Sources used:")
        sources = set()
        for doc in docs:
            source = doc.metadata.get("source", "Unknown")
            sources.add(source)

        for i, source in enumerate(sorted(sources), 1):
            print(f"  {i}. {source}")

        # Provide confidence indicator
        confidence_score = len(
            [
                doc
                for doc in docs
                if question.lower().split()[0] in doc.page_content.lower()
            ]
        )
        total_docs = len(docs)
        confidence = (confidence_score / total_docs) * 100 if total_docs > 0 else 0

        print(
            f"\n📊 Confidence: {confidence:.0f}% (based on keyword presence in sources)"
        )

        return answer

    except Exception as e:
        print(f"❌ Error generating answer: {e}")
        return None


def interactive_mode(rag_chain, retriever):
    """Run in interactive mode for asking multiple questions."""
    print("\n" + "=" * 80)
    print("🎯 INTERACTIVE ATOTI DOCUMENTATION Q&A")
    print("=" * 80)
    print("Ask questions about Atoti Python SDK. Type 'quit' or 'exit' to stop.")
    print("Type 'help' for example questions.")
    print()

    example_questions = [
        "How do I create a session in atoti?",
        "How do I load data from a CSV file?",
        "What is a cube in atoti?",
        "How do I create measures?",
        "How do I connect to a database?",
        "How do I use hierarchies?",
        "How do I secure my atoti session?",
        "What are the different ways to load data?",
        "How do I create calculated measures?",
        "How do I export data from atoti?",
    ]

    while True:
        try:
            question = input("\n❓ Your question: ").strip()

            if not question:
                continue

            if question.lower() in ["quit", "exit", "q"]:
                print("👋 Goodbye!")
                break

            if question.lower() in ["help", "h"]:
                print("\n💡 Example questions you can ask:")
                for i, eq in enumerate(example_questions, 1):
                    print(f"  {i:2d}. {eq}")
                continue

            ask_question(rag_chain, retriever, question)

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except EOFError:
            print("\n\n👋 Goodbye!")
            break


def main():
    """Main function."""
    print("🚀 Starting Atoti Documentation Q&A System")
    print("=" * 60)

    # Load vector database
    vectordb = load_vector_database()

    # Initialize Mistral
    llm, model_name = initialize_mistral()

    # Create RAG chain
    print("🔗 Creating question-answering chain...")
    rag_chain, retriever = create_rag_chain(vectordb, llm)

    print(f"✅ System ready! Using {model_name} for answers.")

    # Check if a question was provided as command line argument
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        ask_question(rag_chain, retriever, question)
    else:
        # Run in interactive mode
        interactive_mode(rag_chain, retriever)


if __name__ == "__main__":
    main()
