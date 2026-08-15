from html import escape


def project_suffix(transaction) -> str:
    project = getattr(transaction, "project", None)
    name = getattr(project, "name", None) if project is not None else None
    if not name:
        return ""
    one_line_name = " ".join(str(name).split())
    return f" 📁 {escape(one_line_name)}"
