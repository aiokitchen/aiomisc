import platform


if platform.system() == "Windows":
    from .process import main
else:
    from .forking import main


if __name__ == "__main__":
    rc = main()
    exit(rc or 0)
