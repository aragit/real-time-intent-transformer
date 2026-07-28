package governance

default allow = false

# Safe actions — always allowed
allow { input.action == "NO_ACTION" }
allow { input.action == "LOG_ANALYTICS" }
allow { input.action == "RECOMMEND_PRODUCT" }
allow { input.action == "OFFER_BUNDLE" }
allow { input.action == "SEND_TO_HUMAN" }
allow { input.action == "LOYALTY_REWARD" }
allow { input.action == "RECOMMEND_ALTERNATIVE" }

# Discount rules (APPLY_DISCOUNT and OFFER_DISCOUNT are synced)
allow {
    not deny
    input.action == "APPLY_DISCOUNT"
    input.customer.discounts_this_month < 3
    input.customer.total_purchases > 0
    input.features.total_cart_value > 50
}

allow {
    not deny
    input.action == "OFFER_DISCOUNT"
    input.customer.discounts_this_month < 3
    input.customer.total_purchases > 0
    input.features.total_cart_value > 50
}

allow {
    not deny
    input.action == "ISSUE_DISCOUNT"
    input.discount_value <= 20
    input.intent != "BROWSING"
}

# Urgency rules
allow {
    not deny
    input.action == "SHOW_URGENCY"
    input.features.inventory_level < 10
    input.features.intent == "CHECKOUT_INTENT"
}

# Abandon email rules
allow {
    not deny
    input.action == "SEND_ABANDON_EMAIL"
    input.features.session_duration_sec > 300
    input.features.cart_adds > 0
    input.features.checkouts == 0
}

# Deny rules — hard limits
deny {
    input.action == "APPLY_DISCOUNT"
    input.customer.last_discount_within_hours < 24
}

deny {
    input.action == "OFFER_DISCOUNT"
    input.customer.last_discount_within_hours < 24
}

deny {
    input.action == "APPLY_DISCOUNT"
    input.customer.demographic_segment != input.features.demographic_segment
}

deny {
    input.action == "OFFER_DISCOUNT"
    input.customer.demographic_segment != input.features.demographic_segment
}

deny {
    input.action == "ISSUE_DISCOUNT"
    input.discount_value > 20
}

deny {
    input.action == "ISSUE_DISCOUNT"
    input.intent == "BROWSING"
}
