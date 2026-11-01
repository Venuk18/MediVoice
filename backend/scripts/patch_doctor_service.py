with open("backend/app/services/doctor_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update get_doctors to use .unique()
old_get_docs = "return list(db.scalars(query).all())"
new_get_docs = "return list(db.scalars(query).unique().all())"
assert old_get_docs in content, "old_get_docs not found"
content = content.replace(old_get_docs, new_get_docs, 1)

# 2. Update search_doctors_tool to use .unique() and stable doctor ID deduplication
old_search = """    doctors = db.scalars(query).all()
    results = []
    for doc in doctors:
        results.append({
            "doctor_id": doc.id,
            "display_name": doc.display_name,
            "specialty": doc.specialty,
            "department_name": doc.department.name if doc.department else "General",
            "hospital_id": doc.hospital_id,
        })
    return results"""

new_search = """    doctors = db.scalars(query).unique().all()
    results = []
    seen_ids = set()
    for doc in doctors:
        if not doc.id or doc.id in seen_ids:
            continue
        seen_ids.add(doc.id)
        results.append({
            "doctor_id": doc.id,
            "display_name": doc.display_name,
            "specialty": doc.specialty,
            "department_name": doc.department.name if doc.department else "General",
            "hospital_id": doc.hospital_id,
        })
    return results"""

old_search_crlf = old_search.replace("\n", "\r\n")
new_search_crlf = new_search.replace("\n", "\r\n")

if old_search_crlf in content:
    content = content.replace(old_search_crlf, new_search_crlf, 1)
elif old_search in content:
    content = content.replace(old_search, new_search, 1)
else:
    raise AssertionError("old_search not found in doctor_service.py")

with open("backend/app/services/doctor_service.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Updated doctor_service.py successfully")

