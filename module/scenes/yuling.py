from module.base_clicker import AutoClicker


def create_yuling(log_fn, port):
    return AutoClicker(log_fn, "yuling", port)
