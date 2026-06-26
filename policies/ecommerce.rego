package ecommerce

default allow = false

allow {
    input.action == "APPLY_DISCOUNT"
    input.customer.discounts_this_month < 3
    input.customer.total_purchases > 0
    input.features.total_cart_value > 50
}

allow {
    input.action == "SHOW_URGENCY"
    input.features.inventory_level < 10
    input.features.intent == "CHECKOUT_INTENT"
}

allow {
    input.action == "SEND_ABANDON_EMAIL"
    input.features.session_duration_sec > 300
    input.features.cart_adds > 0
    input.features.checkouts == 0
}

deny {
    input.action == "APPLY_DISCOUNT"
    input.customer.last_discount_within_hours < 24
}

deny {
    input.action == "APPLY_DISCOUNT"
    input.customer.demographic_segment != input.features.demographic_segment
}
