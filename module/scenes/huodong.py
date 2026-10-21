from module.base_clicker import AutoClicker


def create_huodong(log_fn, port):
    return AutoClicker(log_fn, "huodong", port)
