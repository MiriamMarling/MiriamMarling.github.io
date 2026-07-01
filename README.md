# BonQuery

[![Daily occupancy](https://img.shields.io/github/actions/workflow/status/MiriamMarling/MiriamMarling.github.io/refresh-daily-occupancy.yml?branch=main&label=Daily%20occupancy)](https://github.com/MiriamMarling/MiriamMarling.github.io/actions/workflows/refresh-daily-occupancy.yml) [![Site data](https://img.shields.io/github/actions/workflow/status/MiriamMarling/MiriamMarling.github.io/refresh-site-data.yml?branch=main&label=Site%20data)](https://github.com/MiriamMarling/MiriamMarling.github.io/actions/workflows/refresh-site-data.yml) [![Links](https://img.shields.io/github/actions/workflow/status/MiriamMarling/MiriamMarling.github.io/check-links.yml?branch=main&label=Links)](https://github.com/MiriamMarling/MiriamMarling.github.io/actions/workflows/check-links.yml)

BonQuery breathes life into humanitarian-related data by turning numbers that sit unread on government open-data portals into clear, useful analyses for the people who can do something about the issues behind them.

We use publicly available data to investigate urgent humanitarian issues, starting with Toronto’s shelter system. The work is open, reproducible, and built for journalists, researchers, advocates, policymakers, and anyone paying attention.


🌐 **Website :**  https://bonquery.ca  

**Note:** This repository contains only the front-end website files, aggregated chart data, and rendering configurations for BonQuery.ca. The raw data pipelines, backend processing, and primary analysis scripts are currently kept in a separate, private repository

Website built with the help of [Claude Code](https://claude.com/product/claude-code).

## License

This repository holds the BonQuery.ca front-end (site files, styles, rendering
configuration, and CI workflows) plus the aggregated chart data. The R scripts,
data pipelines, and full replication code live in a separate private repository
and are not covered here.

- **Code** (front-end, styles, configuration, workflows): [MIT License](LICENSE).
  Use, modify, and redistribute freely, keeping the copyright notice.
- **Aggregated chart data and written content**: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  Reuse and adapt freely, provided you credit the source.

**Attribution is required.** If you reuse the data or content, please credit both
BonQuery and the original data source:

> Aggregated data and analysis by Miriam Marling / BonQuery (https://bonquery.ca),
> derived from City of Toronto Open Data, used under the City of Toronto's Open
> Data Licence (https://open.toronto.ca/open-data-licence/).

Crediting the City of Toronto as the original source is a condition of their
licence, not only a courtesy.

# BonQuery

[![Occupation quotidienne](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/MiriamMarling/MiriamMarling.github.io/badges/occupation.json)](https://github.com/MiriamMarling/MiriamMarling.github.io/actions/workflows/refresh-daily-occupancy.yml) [![Données du site](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/MiriamMarling/MiriamMarling.github.io/badges/donnees.json)](https://github.com/MiriamMarling/MiriamMarling.github.io/actions/workflows/refresh-site-data.yml) [![Liens](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/MiriamMarling/MiriamMarling.github.io/badges/liens.json)](https://github.com/MiriamMarling/MiriamMarling.github.io/actions/workflows/check-links.yml)

BonQuery donne vie aux données humanitaires en transformant les chiffres qui dorment sur les portails gouvernementaux de données ouvertes en analyses claires et utiles pour les personnes qui peuvent agir sur les enjeux qu'elles révèlent.

Nous utilisons des données accessibles au public pour analyser des enjeux humanitaires urgents, en commençant par le réseau de refuges de Toronto. Le travail est ouvert, reproductible et conçu pour les journalistes, les chercheurs, les défenseurs, les décideurs politiques et toute personne qui suit la situation de près.

🌐 **Site web :** https://bonquery.ca

**Note :** Ce dépôt contient uniquement les fichiers du site front-end, les données agrégées utilisées pour les graphiques et les configurations de rendu de BonQuery.ca. Les pipelines de données brutes, le traitement backend et les scripts d'analyse principaux sont actuellement conservés dans un dépôt privé distinct.

Site web développé avec l’aide de [Claude Code](https://claude.com/product/claude-code).

## Licence

Ce dépôt contient l'interface (« front-end ») de BonQuery.ca : fichiers du site,
styles, configuration de rendu et workflows d'intégration continue, ainsi que les
données agrégées des graphiques. Les scripts R, les pipelines de données et le code
complet de reproduction se trouvent dans un dépôt privé distinct et ne sont pas
visés ici.

- **Code** (interface, styles, configuration, workflows) : [licence MIT](LICENSE).
  Utilisation, modification et redistribution libres, en conservant l'avis de droit
  d'auteur.
- **Données agrégées et contenu rédactionnel** : [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  Réutilisation et adaptation libres, à condition de créditer la source.

**La mention de la source est obligatoire.** Si vous réutilisez les données ou le
contenu, veuillez créditer à la fois BonQuery et la source d'origine des données :

> Données agrégées et analyse par Miriam Marling / BonQuery (https://bonquery.ca),
> dérivées des données ouvertes de la Ville de Toronto, utilisées selon la licence
> des données ouvertes de la Ville de Toronto (https://open.toronto.ca/open-data-licence/).

Créditer la Ville de Toronto comme source d'origine est une condition de sa licence,
et non une simple courtoisie.
