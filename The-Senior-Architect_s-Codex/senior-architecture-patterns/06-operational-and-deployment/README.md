
# 🚢 Group 6: Operational & Deployment

## Overview

**"It works on my machine" is not a deployment strategy.**

Writing code is the easy part. Getting that code into production reliably, without downtime, and ensuring it runs consistently across 100 servers is the hard part. This module shifts focus from *Code Architecture* to *Infrastructure Architecture*.

These patterns move you away from "Pet" servers (hand-crafted, fragile) to "Cattle" servers (automated, disposable). They introduce safety nets that allow you to deploy at 2 PM on a Friday without fear.

## 📜 Pattern Index

| Pattern | Goal | Senior "Soundbite" |
| :--- | :--- | :--- |
| **[23. Blue-Green Deployment](https://www.google.com/search?q=./23-blue-green-deployment.md)** | **Zero Downtime** | "Spin up the new version next to the old one. Switch the traffic instantly. If it breaks, switch back." |
| **[24. Canary Release](https://www.google.com/search?q=./24-canary-release.md)** | **Risk Reduction** | "Don't give the new update to everyone. Give it to 1% of users and see if they survive." |
| **[25. Immutable Infrastructure](https://www.google.com/search?q=./25-immutable-infrastructure.md)** | **Consistency** | "Never patch a running server. If you need to change a config, build a new image and replace the server." |

## 🧠 The Operational Checklist

Before approving a deployment strategy, a Senior Architect asks:

1.  **The "Undo" Test:** If the deployment fails 30 seconds after go-live, can we revert to the previous version in under 1 minute? (Blue-Green allows this).
2.  **The "Blast Radius" Test:** If we ship a critical bug, does it take down the entire platform, or just affect a small group? (Canary limits this).
3.  **The "Drift" Test:** Are the servers running in production exactly the same as the ones we tested in staging? Or has someone manually tweaked the `nginx.conf` on Prod-Server-05? (Immutable Infrastructure prevents this).
4.  **The "Database" Test:** Does the database schema support *both* the old code and the new code running simultaneously? (Required for all zero-downtime patterns).

## ⚠️ Common Pitfalls in This Module

  * **Infrastructure as ClickOps:** Manually clicking around the AWS Console to create servers. This is unrepeatable and dangerous. Use Terraform/CloudFormation.
  * **Ignoring the Database:** Implementing fancy Blue-Green deployments for the code but forgetting that a database migration locks the table for 10 minutes, causing downtime anyway.
  * **Lack of Observability:** Doing a Canary release without having the dashboards to actually tell if the Canary is failing.


