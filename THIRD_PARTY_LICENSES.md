# Third-party licenses

The diagram-design skill itself is MIT-licensed (see [`LICENSE`](LICENSE)). It bundles content from the following third-party sources, redistributed under their respective licenses.

## Tabler Icons

- **License:** MIT
- **Upstream:** https://github.com/tabler/tabler-icons
- **Used in:** stroked icons in `skills/diagram-design/references/primitive-icons.md` and `skills/diagram-design/assets/icons.html` (categories: Compute, People, Network, Data, Kubernetes, Action, DevOps, plus the stroked Brand outlines for Docker, Terraform, AWS, Azure, GitHub).

The MIT license is reproduced in full at https://github.com/tabler/tabler-icons/blob/main/LICENSE.

## Simple Icons

- **License:** CC0 1.0 Universal (Public Domain Dedication)
- **Upstream:** https://github.com/simple-icons/simple-icons
- **Used in:** filled brand silhouettes in `skills/diagram-design/references/primitive-icons.md` and `skills/diagram-design/assets/icons.html` (Kubernetes, Google Cloud, PostgreSQL, Nginx, Gitea, Keycloak, MinIO, Apache NiFi, Apache Airflow, Trino, Apache Superset, Jupyter, Python, R).

The CC0 dedication is reproduced in full at https://github.com/simple-icons/simple-icons/blob/develop/LICENSE.md.

## log-z/logos

- **License:** MIT
- **Upstream:** https://github.com/log-z/logos/tree/main/website-logos
- **Used in:** filled brand silhouettes that aren't carried by Simple Icons or Tabler — currently MySQL, Redis, and StarRocks. Source SVGs are 100×100 with embedded `<style>` + class-based fills; the build script strips the style block and rewrites class refs to `currentColor` for monochrome consistency.

The MIT license is reproduced in full at https://github.com/log-z/logos/blob/main/LICENSE.

## Devicon

- **License:** MIT
- **Upstream:** https://github.com/devicons/devicon
- **Used in:** the RStudio and SPSS icons in `scripts/vendor/icons/devicon/`.

The MIT license is reproduced in full at https://github.com/devicons/devicon/blob/master/LICENSE.

## One-off sourced icons

The `scripts/vendor/icons/url/` directory contains one-off sourced icons for SAS, from [SVGRepo](https://www.svgrepo.com/download/374062/sas.svg), and Stata, from the [IcePanel Technology Icons collection](https://icon.icepanel.io/Technology/svg/Stata.svg) published via techicons.dev. Their provenance is recorded here; use of these product marks is covered by the Trademarks note below.

## Trademarks

Brand logos remain the trademarks of their respective owners. Their inclusion in this icon set is for documentation and illustrative use only. The presence of a brand mark in this repository does not imply endorsement, sponsorship, or affiliation.
