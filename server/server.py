"""Zotero PDF2zh Server command-line entry point."""

__version__ = "4.1.9-beta.6"

if __name__ == "__main__":
    from pdf2zh_server.startup import main

    main(__version__)
