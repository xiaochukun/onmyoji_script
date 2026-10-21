from module.tupo_clicker import AutoClicker


def create_tupo(log_fn, port, ticket_limit=0):
    return AutoClicker(log_fn, "tupo", port, ticket_limit=ticket_limit)