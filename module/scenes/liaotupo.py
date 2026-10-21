from module.tupo_clicker import AutoClicker


def create_liaotupo(log_fn, port, ticket_limit=0):
    return AutoClicker(log_fn, "liaotupo", port,
                       ticket_limit=ticket_limit, check_ticket=False)
