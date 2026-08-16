"""Shared test composition for the bundled species catalog."""

from elfie.profile import configure_species_catalog
from infrastructure.persistence.configuration.species import load_species_catalog


configure_species_catalog(load_species_catalog())
