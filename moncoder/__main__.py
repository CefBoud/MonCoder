from .config import init


def main():
    init()  # must init before importing run
    from .chat import run

    run()


if __name__ == "__main__":
    main()
