package governance

default allow = false

# Rule 3 (Safe Actions): Explicitly allow harmless analytical actions
allow if {
    input.action == "LOG_ANALYTICS"
}

allow if {
    input.action == "RECOMMEND_PRODUCT"
}

# Rule 1 (Hard Limit): Deny any ISSUE_DISCOUNT where discount_value > 20%
deny if {
    input.action == "ISSUE_DISCOUNT"
    input.discount_value > 20
}

# Rule 2 (Intent Guard): Deny ISSUE_DISCOUNT if intent is BROWSING
deny if {
    input.action == "ISSUE_DISCOUNT"
    input.intent == "BROWSING"
}

# Allow ISSUE_DISCOUNT only when discount <= 20% AND intent is not BROWSING
allow if {
    input.action == "ISSUE_DISCOUNT"
    input.discount_value <= 20
    input.intent != "BROWSING"
}
