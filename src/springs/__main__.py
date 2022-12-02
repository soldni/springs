from .commandline import cli


@cli()
def main(_):
    raise RuntimeError(
        "This should never be called. Please use springs.cli "
        "to decorate your program's main function instead."
    )


if __name__ == "__main__":
    main()
