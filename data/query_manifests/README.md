# Query manifests

Each JSON file in this directory is a deterministic list of official OECD and Eurostat requests for one proposed source vintage.

The adjacent `.audit.csv` records whether the expected raw payload for every query is currently missing, unverified, invalid, or SHA-256 verified.

A publication data release is complete only when all rows are `verified`.
