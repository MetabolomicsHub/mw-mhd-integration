import click


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """Metabomics Workbench - MHD Integration CLI with subcommands."""
    pass
