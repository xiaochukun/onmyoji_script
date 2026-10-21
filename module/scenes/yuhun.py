from module.base_clicker import AutoClicker


def create_yuhun(log_fn, port):
    return AutoClicker(log_fn, "yuhun", port)
