import copy

COLLECTIONS = {"fact": ("facts", "fact_id"), "timeline": ("timeline", "event_id"), "issue": ("legal_issues", "issue_id"), "incident": ("incidents", "incident_id"), "mapping": ("evidence_issue_mapping", "issue_id")}


def apply_overrides(data, overrides):
    for entry in overrides:
        kind, identifier = entry["target"].split(":", 1)
        value = copy.deepcopy(entry["new"])
        if kind in COLLECTIONS:
            collection, key = COLLECTIONS[kind]
            values = data.setdefault(collection, [])
            index = next((n for n, item in enumerate(values) if item[key] == identifier), None)
            if index is None: values.append(value)
            else: values[index] = value
        elif kind in {"party", "forum", "limitation", "temporal_law"}:
            data["parties" if kind == "party" else kind] = value
        elif kind in {"provision", "pending"}:
            for collection in ("applicable_law", "pending_advocate_verification"):
                data[collection] = [item for item in data.get(collection, []) if item.get("provision_id") != identifier]
            destination = "applicable_law" if value.get("verification_status") == "VERIFIED" else "pending_advocate_verification"
            data[destination].append(value)
    return data
