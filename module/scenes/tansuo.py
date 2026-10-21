from module.tansuo_clicker import  AutoClicker


def create_tansuo(log_fn, port):
    return AutoClicker(log_fn, "tansuo", port)
