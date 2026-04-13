#!/usr/bin/env python3
"""Generate README.md files for all connectors that don't have one.

Reads connector specs and tool_metadata to produce comprehensive,
template-compliant documentation for each connector.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "webapp"))

from toolsconnector.serve import list_connectors
from toolsconnector.codegen import extract_spec
from tool_metadata import get_tool_meta

# ── Rich metadata for connectors NOT in tool_metadata.py ──────────────
# Keys that tool_metadata already has will be kept; these fill the gaps.
EXTRA_META: dict[str, dict] = {
    "airtable": {
        "company": "Airtable Inc.",
        "website": "https://airtable.com",
        "docs": "https://airtable.com/developers/web/api/introduction",
        "logo": "https://cdn.simpleicons.org/airtable",
        "color": "#18BFFF",
        "tagline": "Flexible database-spreadsheet hybrid for teams",
        "overview": "The Airtable API lets you create, read, update, and delete records in your Airtable bases. Manage tables, fields, views, and webhooks. Build data-driven apps, content calendars, and project trackers backed by Airtable's flexible schema.",
        "use_cases": ["Content calendar management", "CRM and lead tracking", "Project management", "Inventory management", "Survey and form data collection"],
        "auth_methods": ["Personal Access Token", "OAuth 2.0"],
        "pricing": "Free tier, Team from $20/seat/month",
        "rate_limit": "5 requests/second per base",
        "get_credentials_url": "https://airtable.com/create/tokens",
    },
    "asana": {
        "company": "Asana Inc.",
        "website": "https://asana.com",
        "docs": "https://developers.asana.com/reference/rest-api-reference",
        "logo": "https://cdn.simpleicons.org/asana",
        "color": "#F06A6A",
        "tagline": "Work management and project tracking for teams",
        "overview": "The Asana API lets you manage tasks, projects, sections, and teams programmatically. Create workflows, track work status, manage assignments, and build custom integrations with Asana's work management platform.",
        "use_cases": ["Task automation", "Project tracking dashboards", "Cross-tool workflow sync", "Sprint management", "Team workload reporting"],
        "auth_methods": ["Personal Access Token", "OAuth 2.0"],
        "pricing": "Free tier, Premium from $10.99/user/month",
        "rate_limit": "150 requests/minute",
        "get_credentials_url": "https://app.asana.com/0/my-apps",
    },
    "auth0": {
        "company": "Okta (Auth0)",
        "website": "https://auth0.com",
        "docs": "https://auth0.com/docs/api/management/v2",
        "logo": "https://cdn.simpleicons.org/auth0",
        "color": "#EB5424",
        "tagline": "Identity platform for authentication and authorization",
        "overview": "The Auth0 Management API lets you manage users, connections, roles, and applications in your Auth0 tenant. Configure authentication flows, manage user profiles, assign permissions, and monitor security events.",
        "use_cases": ["User management", "Role-based access control", "SSO configuration", "Passwordless authentication", "Security auditing"],
        "auth_methods": ["Bearer Token (Management API Token)"],
        "pricing": "Free up to 7,500 MAUs, Professional from $240/month",
        "rate_limit": "Varies by endpoint (typically 50-100/sec)",
        "get_credentials_url": "https://manage.auth0.com/#/apis/management/explorer",
    },
    "calendly": {
        "company": "Calendly LLC",
        "website": "https://calendly.com",
        "docs": "https://developer.calendly.com/api-docs",
        "logo": "https://cdn.simpleicons.org/calendly",
        "color": "#006BFF",
        "tagline": "Scheduling automation for meetings and events",
        "overview": "The Calendly API provides access to event types, scheduled events, invitees, and scheduling links. Automate meeting scheduling, sync calendar data, manage availability, and build custom booking experiences.",
        "use_cases": ["Meeting scheduling automation", "Calendar sync", "Event analytics", "Custom booking pages", "Sales pipeline integration"],
        "auth_methods": ["Personal Access Token", "OAuth 2.0"],
        "pricing": "Free tier, Standard from $10/seat/month",
        "rate_limit": "200 requests/minute",
        "get_credentials_url": "https://calendly.com/integrations/api_webhooks",
    },
    "cloudflare": {
        "company": "Cloudflare Inc.",
        "website": "https://cloudflare.com",
        "docs": "https://developers.cloudflare.com/api/",
        "logo": "https://cdn.simpleicons.org/cloudflare",
        "color": "#F38020",
        "tagline": "CDN, DNS, security, and edge computing platform",
        "overview": "The Cloudflare API provides access to DNS records, zones, firewall rules, Workers, and more. Manage your web infrastructure, configure security policies, deploy serverless functions, and monitor traffic analytics.",
        "use_cases": ["DNS management", "CDN configuration", "Web security rules", "Edge worker deployment", "Traffic analytics"],
        "auth_methods": ["API Token", "API Key + Email"],
        "pricing": "Free tier, Pro from $20/month",
        "rate_limit": "1,200 requests/5 minutes",
        "get_credentials_url": "https://dash.cloudflare.com/profile/api-tokens",
    },
    "confluence": {
        "company": "Atlassian",
        "website": "https://www.atlassian.com/software/confluence",
        "docs": "https://developer.atlassian.com/cloud/confluence/rest/v2/intro/",
        "logo": "https://cdn.simpleicons.org/confluence",
        "color": "#172B4D",
        "tagline": "Team wiki, documentation, and knowledge management",
        "overview": "The Confluence REST API provides access to spaces, pages, blog posts, comments, and attachments. Create and organize documentation, search content, manage permissions, and build knowledge management workflows.",
        "use_cases": ["Documentation automation", "Knowledge base management", "Content publishing", "Team collaboration", "Compliance documentation"],
        "auth_methods": ["Basic Auth (email:api_token)", "OAuth 2.0"],
        "pricing": "Free up to 10 users, Standard from $6.05/user/month",
        "rate_limit": "100 requests/minute",
        "get_credentials_url": "https://id.atlassian.com/manage-profile/security/api-tokens",
    },
    "datadog": {
        "company": "Datadog Inc.",
        "website": "https://datadoghq.com",
        "docs": "https://docs.datadoghq.com/api/latest/",
        "logo": "https://cdn.simpleicons.org/datadog",
        "color": "#632CA6",
        "tagline": "Monitoring, APM, and log management platform",
        "overview": "The Datadog API lets you manage dashboards, monitors, metrics, logs, and incidents. Query time-series data, create alerts, manage service catalogs, and build observability automation for your infrastructure.",
        "use_cases": ["Infrastructure monitoring", "Alert management", "Dashboard automation", "Log analysis", "Incident response"],
        "auth_methods": ["API Key + Application Key"],
        "pricing": "Free tier, Pro from $15/host/month",
        "rate_limit": "300 requests/hour for some endpoints",
        "get_credentials_url": "https://app.datadoghq.com/organization-settings/api-keys",
    },
    "dockerhub": {
        "company": "Docker Inc.",
        "website": "https://hub.docker.com",
        "docs": "https://docs.docker.com/docker-hub/api/latest/",
        "logo": "https://cdn.simpleicons.org/docker",
        "color": "#2496ED",
        "tagline": "Container registry and image management",
        "overview": "The Docker Hub API provides access to repositories, images, tags, and organizations. Search for images, manage repository settings, check image vulnerabilities, and automate container image lifecycle management.",
        "use_cases": ["Image registry management", "Vulnerability scanning automation", "CI/CD image publishing", "Repository access control", "Image tag management"],
        "auth_methods": ["Personal Access Token"],
        "pricing": "Free tier, Pro from $5/month",
        "rate_limit": "100 pulls/6 hours (anonymous), 200 (authenticated)",
        "get_credentials_url": "https://hub.docker.com/settings/security",
    },
    "figma": {
        "company": "Figma Inc. (Adobe)",
        "website": "https://figma.com",
        "docs": "https://www.figma.com/developers/api",
        "logo": "https://cdn.simpleicons.org/figma",
        "color": "#F24E1E",
        "tagline": "Collaborative design and prototyping tool",
        "overview": "The Figma API provides access to files, components, styles, comments, and project metadata. Extract design tokens, automate asset export, manage team libraries, and build design-to-code workflows.",
        "use_cases": ["Design token extraction", "Automated asset export", "Design system management", "Comment and review automation", "Design analytics"],
        "auth_methods": ["Personal Access Token", "OAuth 2.0"],
        "pricing": "Free tier, Professional from $15/editor/month",
        "rate_limit": "30 requests/minute per token",
        "get_credentials_url": "https://www.figma.com/developers/api#access-tokens",
    },
    "firestore": {
        "company": "Google (Firebase)",
        "website": "https://firebase.google.com/products/firestore",
        "docs": "https://firebase.google.com/docs/firestore/reference/rest",
        "logo": "https://cdn.simpleicons.org/firebase",
        "color": "#FFCA28",
        "tagline": "Serverless NoSQL document database",
        "overview": "The Firestore REST API provides access to documents and collections in your Firebase Firestore database. Query data with filters and ordering, perform batch operations, manage indexes, and build real-time applications.",
        "use_cases": ["Document storage and retrieval", "Real-time data sync", "Serverless backend", "Mobile app data layer", "IoT data collection"],
        "auth_methods": ["Bearer Token (Firebase Auth)", "Service Account"],
        "pricing": "Free tier (Spark), Pay-as-you-go (Blaze)",
        "rate_limit": "Varies by plan",
        "get_credentials_url": "https://console.firebase.google.com/",
    },
    "freshdesk": {
        "company": "Freshworks Inc.",
        "website": "https://freshdesk.com",
        "docs": "https://developers.freshdesk.com/api/",
        "logo": "https://cdn.simpleicons.org/freshdesk/2D93F1",
        "color": "#2D93F1",
        "tagline": "Customer support and helpdesk platform",
        "overview": "The Freshdesk API provides access to tickets, contacts, agents, companies, and knowledge base articles. Manage support workflows, automate ticket routing, track SLAs, and build custom helpdesk integrations.",
        "use_cases": ["Ticket management", "Customer support automation", "Knowledge base management", "SLA tracking", "Multi-channel support"],
        "auth_methods": ["API Key"],
        "pricing": "Free up to 10 agents, Growth from $15/agent/month",
        "rate_limit": "Varies by plan (min 50 requests/minute)",
        "get_credentials_url": "https://support.freshdesk.com/en/support/solutions/articles/215517",
    },
    "intercom": {
        "company": "Intercom Inc.",
        "website": "https://intercom.com",
        "docs": "https://developers.intercom.com/docs/references/rest-api/api.intercom.io/",
        "logo": "https://cdn.simpleicons.org/intercom",
        "color": "#6AFDEF",
        "tagline": "Customer messaging and engagement platform",
        "overview": "The Intercom API provides access to contacts, conversations, articles, teams, and tags. Manage customer communication, automate messaging workflows, build help center content, and integrate with your CRM.",
        "use_cases": ["Customer communication", "In-app messaging", "Help center management", "Lead qualification", "User engagement tracking"],
        "auth_methods": ["Bearer Token (Access Token)"],
        "pricing": "From $39/seat/month",
        "rate_limit": "Varies by plan and endpoint",
        "get_credentials_url": "https://app.intercom.com/a/apps/_/developer-hub",
    },
    "linear": {
        "company": "Linear Inc.",
        "website": "https://linear.app",
        "docs": "https://developers.linear.app/docs/graphql/working-with-the-graphql-api",
        "logo": "https://cdn.simpleicons.org/linear",
        "color": "#5E6AD2",
        "tagline": "Streamlined issue tracking for software teams",
        "overview": "The Linear GraphQL API provides access to issues, projects, cycles, teams, and labels. Track bugs and features, manage sprints, automate workflows, and build integrations with Linear's modern project management platform.",
        "use_cases": ["Issue tracking", "Sprint management", "Bug triage automation", "Development workflow", "Cross-tool project sync"],
        "auth_methods": ["API Key", "OAuth 2.0"],
        "pricing": "Free tier, Plus from $8/user/month",
        "rate_limit": "400 requests/minute",
        "get_credentials_url": "https://linear.app/settings/api",
    },
    "mailchimp": {
        "company": "Intuit (Mailchimp)",
        "website": "https://mailchimp.com",
        "docs": "https://mailchimp.com/developer/marketing/api/",
        "logo": "https://cdn.simpleicons.org/mailchimp",
        "color": "#FFE01B",
        "tagline": "Email marketing and audience management",
        "overview": "The Mailchimp Marketing API provides access to audiences, campaigns, templates, and automations. Manage subscriber lists, create and send email campaigns, set up automation workflows, and track engagement analytics.",
        "use_cases": ["Email campaign management", "Subscriber list management", "Marketing automation", "A/B testing", "Engagement analytics"],
        "auth_methods": ["API Key"],
        "pricing": "Free up to 500 contacts, Essentials from $13/month",
        "rate_limit": "10 concurrent connections",
        "get_credentials_url": "https://mailchimp.com/help/about-api-keys/",
    },
    "mixpanel": {
        "company": "Mixpanel Inc.",
        "website": "https://mixpanel.com",
        "docs": "https://developer.mixpanel.com/reference/overview",
        "logo": "https://cdn.simpleicons.org/mixpanel",
        "color": "#7856FF",
        "tagline": "Product analytics and user behavior tracking",
        "overview": "The Mixpanel API lets you track events, query analytics data, manage user profiles, and export data. Build product analytics pipelines, create funnels, analyze user retention, and automate reporting workflows.",
        "use_cases": ["Event tracking", "Funnel analysis", "User retention reporting", "A/B test analysis", "Data export and ETL"],
        "auth_methods": ["Service Account (Basic Auth)"],
        "pricing": "Free up to 20M events, Growth from $28/month",
        "rate_limit": "Varies by endpoint",
        "get_credentials_url": "https://mixpanel.com/settings/project#serviceaccounts",
    },
    "mongodb": {
        "company": "MongoDB Inc.",
        "website": "https://www.mongodb.com/atlas",
        "docs": "https://www.mongodb.com/docs/atlas/api/",
        "logo": "https://cdn.simpleicons.org/mongodb",
        "color": "#47A248",
        "tagline": "Cloud-hosted NoSQL document database",
        "overview": "The MongoDB Atlas Data API provides RESTful access to your MongoDB Atlas clusters. Query documents, run aggregation pipelines, insert and update data, and manage collections without direct driver connections.",
        "use_cases": ["Document CRUD operations", "Aggregation pipelines", "Serverless data access", "Edge data queries", "Cross-platform data sync"],
        "auth_methods": ["API Key"],
        "pricing": "Free tier (M0), Dedicated from $57/month",
        "rate_limit": "300 requests/minute (Data API)",
        "get_credentials_url": "https://cloud.mongodb.com/",
    },
    "okta": {
        "company": "Okta Inc.",
        "website": "https://okta.com",
        "docs": "https://developer.okta.com/docs/reference/",
        "logo": "https://cdn.simpleicons.org/okta",
        "color": "#007DC1",
        "tagline": "Enterprise identity and access management",
        "overview": "The Okta API provides access to users, groups, applications, and system logs. Manage enterprise identity lifecycle, configure SSO, enforce MFA, audit security events, and automate user provisioning.",
        "use_cases": ["User lifecycle management", "SSO configuration", "Group and role management", "Security audit logging", "Application provisioning"],
        "auth_methods": ["API Token", "OAuth 2.0"],
        "pricing": "Contact sales (SSO from $2/user/month)",
        "rate_limit": "Varies by endpoint (typically 600/min)",
        "get_credentials_url": "https://developer.okta.com/docs/guides/create-an-api-token/main/",
    },
    "outlook": {
        "company": "Microsoft",
        "website": "https://outlook.com",
        "docs": "https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview",
        "logo": "https://cdn.simpleicons.org/microsoftoutlook",
        "color": "#0078D4",
        "tagline": "Email, calendar, and contacts via Microsoft Graph",
        "overview": "The Microsoft Graph Mail API provides access to Outlook email, calendar, and contacts. Read, send, and organize emails, manage calendar events, and work with contact data across Microsoft 365 accounts.",
        "use_cases": ["Email automation", "Calendar management", "Contact sync", "Meeting scheduling", "Email analytics"],
        "auth_methods": ["OAuth 2.0 (Microsoft Graph)"],
        "pricing": "Included with Microsoft 365",
        "rate_limit": "10,000 requests/10 minutes per app",
        "get_credentials_url": "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps",
    },
    "pagerduty": {
        "company": "PagerDuty Inc.",
        "website": "https://pagerduty.com",
        "docs": "https://developer.pagerduty.com/api-reference/",
        "logo": "https://cdn.simpleicons.org/pagerduty",
        "color": "#06AC38",
        "tagline": "Incident management and on-call scheduling",
        "overview": "The PagerDuty API provides access to incidents, services, users, schedules, and escalation policies. Automate incident response, manage on-call rotations, trigger and resolve alerts, and build custom monitoring integrations.",
        "use_cases": ["Incident management", "On-call scheduling", "Alert automation", "Escalation policy management", "Service health dashboards"],
        "auth_methods": ["API Key"],
        "pricing": "Free up to 5 users, Professional from $21/user/month",
        "rate_limit": "960 requests/minute",
        "get_credentials_url": "https://support.pagerduty.com/main/docs/api-access-keys",
    },
    "pinecone": {
        "company": "Pinecone Systems Inc.",
        "website": "https://pinecone.io",
        "docs": "https://docs.pinecone.io/reference/api/introduction",
        "logo": "https://cdn.simpleicons.org/pinecone",
        "color": "#000000",
        "tagline": "Vector database for AI and machine learning",
        "overview": "The Pinecone API provides vector database operations for AI applications. Upsert, query, and manage high-dimensional vector embeddings. Build semantic search, recommendation engines, RAG pipelines, and anomaly detection systems.",
        "use_cases": ["Semantic search", "RAG (Retrieval-Augmented Generation)", "Recommendation engines", "Anomaly detection", "Image similarity"],
        "auth_methods": ["API Key"],
        "pricing": "Free tier (Starter), Standard from $70/month",
        "rate_limit": "Varies by plan and pod type",
        "get_credentials_url": "https://app.pinecone.io/",
    },
    "plaid": {
        "company": "Plaid Inc.",
        "website": "https://plaid.com",
        "docs": "https://plaid.com/docs/api/",
        "logo": "https://cdn.simpleicons.org/plaid/000000",
        "color": "#0A85EA",
        "tagline": "Financial data connectivity and banking APIs",
        "overview": "The Plaid API provides access to financial account data, transactions, balances, and identity information. Connect to bank accounts, verify identity, check balances, categorize transactions, and power fintech applications.",
        "use_cases": ["Bank account linking", "Transaction history", "Balance verification", "Identity verification", "Financial data aggregation"],
        "auth_methods": ["API Key (Client ID + Secret)"],
        "pricing": "Pay per connection (custom pricing)",
        "rate_limit": "Varies by product",
        "get_credentials_url": "https://dashboard.plaid.com/team/keys",
    },
    "rabbitmq": {
        "company": "VMware (Broadcom)",
        "website": "https://rabbitmq.com",
        "docs": "https://rawcdn.githack.com/rabbitmq/rabbitmq-server/v4.1.1/deps/rabbitmq_management/priv/www/api/index.html",
        "logo": "https://cdn.simpleicons.org/rabbitmq",
        "color": "#FF6600",
        "tagline": "Open-source message broker and queue management",
        "overview": "The RabbitMQ Management HTTP API provides access to exchanges, queues, bindings, connections, and channels. Monitor broker health, manage queue configurations, publish and consume messages, and build reliable messaging workflows.",
        "use_cases": ["Message queue management", "Broker monitoring", "Queue configuration", "Exchange and binding setup", "Dead letter handling"],
        "auth_methods": ["Basic Auth"],
        "pricing": "Free (open-source), CloudAMQP from $0/month",
        "rate_limit": "No hard limit (management API)",
        "get_credentials_url": "https://rabbitmq.com/docs/management",
    },
    "redis": {
        "company": "Upstash Inc.",
        "website": "https://upstash.com",
        "docs": "https://upstash.com/docs/redis/overall/getstarted",
        "logo": "https://cdn.simpleicons.org/redis",
        "color": "#DC382D",
        "tagline": "Serverless Redis with HTTP API",
        "overview": "The Upstash Redis REST API provides HTTP-based access to Redis data structures. Execute Redis commands over HTTP, manage keys, work with strings, lists, sets, hashes, and sorted sets without maintaining persistent connections.",
        "use_cases": ["Serverless caching", "Session management", "Rate limiting", "Real-time leaderboards", "Pub/sub messaging"],
        "auth_methods": ["Bearer Token"],
        "pricing": "Free tier (10K commands/day), Pay-as-you-go from $0.2/100K commands",
        "rate_limit": "1,000 requests/second",
        "get_credentials_url": "https://console.upstash.com/",
    },
    "s3": {
        "company": "Amazon Web Services",
        "website": "https://aws.amazon.com/s3/",
        "docs": "https://docs.aws.amazon.com/AmazonS3/latest/API/",
        "logo": "https://cdn.simpleicons.org/amazons3",
        "color": "#569A31",
        "tagline": "Scalable object storage in the cloud",
        "overview": "The AWS S3 API provides object storage operations for buckets and objects. Upload, download, list, and manage files. Configure lifecycle policies, access permissions, versioning, and static website hosting.",
        "use_cases": ["File storage and retrieval", "Static website hosting", "Data lake storage", "Backup and archival", "Content distribution"],
        "auth_methods": ["AWS SigV4 (Access Key + Secret Key)"],
        "pricing": "Pay-per-use (from $0.023/GB/month)",
        "rate_limit": "5,500 GET/sec, 3,500 PUT/sec per prefix",
        "get_credentials_url": "https://console.aws.amazon.com/iam/home#/security_credentials",
    },
    "segment": {
        "company": "Twilio (Segment)",
        "website": "https://segment.com",
        "docs": "https://segment.com/docs/api/",
        "logo": "https://cdn.simpleicons.org/segment",
        "color": "#52BD95",
        "tagline": "Customer data platform and event tracking",
        "overview": "The Segment API provides access to sources, destinations, tracking events, and user profiles. Collect and route customer data, manage tracking plans, configure destinations, and build unified customer data pipelines.",
        "use_cases": ["Event tracking", "Customer data routing", "Analytics pipeline management", "Data governance", "User profile unification"],
        "auth_methods": ["Bearer Token (API Token)"],
        "pricing": "Free tier, Team from $120/month",
        "rate_limit": "100 requests/second",
        "get_credentials_url": "https://app.segment.com/",
    },
    "sendgrid": {
        "company": "Twilio (SendGrid)",
        "website": "https://sendgrid.com",
        "docs": "https://docs.sendgrid.com/api-reference",
        "logo": "https://cdn.simpleicons.org/sendgrid/51A9E3",
        "color": "#51A9E3",
        "tagline": "Transactional and marketing email delivery",
        "overview": "The SendGrid API provides email sending, template management, contact lists, and analytics. Send transactional and marketing emails at scale, manage dynamic templates, track opens and clicks, and maintain sender reputation.",
        "use_cases": ["Transactional email", "Marketing campaigns", "Email template management", "Delivery analytics", "Sender reputation management"],
        "auth_methods": ["API Key"],
        "pricing": "Free up to 100 emails/day, Essentials from $19.95/month",
        "rate_limit": "Varies by plan",
        "get_credentials_url": "https://app.sendgrid.com/settings/api_keys",
    },
    "shopify": {
        "company": "Shopify Inc.",
        "website": "https://shopify.com",
        "docs": "https://shopify.dev/docs/api/admin-rest",
        "logo": "https://cdn.simpleicons.org/shopify",
        "color": "#7AB55C",
        "tagline": "E-commerce platform for online stores",
        "overview": "The Shopify Admin API provides access to products, orders, customers, inventory, and fulfillments. Manage your online store, process orders, track inventory, handle refunds, and build custom e-commerce integrations.",
        "use_cases": ["Product catalog management", "Order processing", "Inventory tracking", "Customer management", "Fulfillment automation"],
        "auth_methods": ["API Key (Admin API Access Token)"],
        "pricing": "Basic from $39/month",
        "rate_limit": "40 requests/second (Plus: 80/sec)",
        "get_credentials_url": "https://shopify.dev/docs/apps/build/authentication/access-tokens",
    },
    "sqs": {
        "company": "Amazon Web Services",
        "website": "https://aws.amazon.com/sqs/",
        "docs": "https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/",
        "logo": "https://cdn.simpleicons.org/amazonsqs",
        "color": "#FF4F8B",
        "tagline": "Fully managed message queuing service",
        "overview": "The AWS SQS API provides message queuing operations for decoupling distributed systems. Send, receive, and delete messages. Manage queues, configure dead-letter queues, and build reliable event-driven architectures.",
        "use_cases": ["Microservice decoupling", "Task queuing", "Event-driven architectures", "Batch processing", "Dead-letter queue management"],
        "auth_methods": ["AWS SigV4 (Access Key + Secret Key)"],
        "pricing": "Free tier (1M requests/month), then $0.40/million",
        "rate_limit": "Unlimited (Standard), 300 msg/sec (FIFO)",
        "get_credentials_url": "https://console.aws.amazon.com/iam/home#/security_credentials",
    },
    "supabase": {
        "company": "Supabase Inc.",
        "website": "https://supabase.com",
        "docs": "https://supabase.com/docs/guides/api",
        "logo": "https://cdn.simpleicons.org/supabase",
        "color": "#3FCF8E",
        "tagline": "Open-source Firebase alternative with Postgres",
        "overview": "The Supabase API provides RESTful access to your Postgres database, authentication, and storage. Query tables, manage rows, handle file uploads, and build full-stack applications with Supabase's auto-generated API.",
        "use_cases": ["Database CRUD operations", "User authentication", "File storage", "Real-time subscriptions", "Serverless backends"],
        "auth_methods": ["API Key (anon/service_role)"],
        "pricing": "Free tier, Pro from $25/month",
        "rate_limit": "Varies by plan",
        "get_credentials_url": "https://supabase.com/dashboard/",
    },
    "teams": {
        "company": "Microsoft",
        "website": "https://teams.microsoft.com",
        "docs": "https://learn.microsoft.com/en-us/graph/api/resources/teams-api-overview",
        "logo": "https://cdn.simpleicons.org/microsoftteams",
        "color": "#6264A7",
        "tagline": "Team collaboration, messaging, and meetings",
        "overview": "The Microsoft Teams API (via Microsoft Graph) provides access to teams, channels, messages, and members. Send messages, manage team membership, create channels, and build collaboration workflows for Microsoft 365.",
        "use_cases": ["Team messaging automation", "Channel management", "Meeting scheduling", "Notification bots", "Workflow integrations"],
        "auth_methods": ["OAuth 2.0 (Microsoft Graph)"],
        "pricing": "Included with Microsoft 365",
        "rate_limit": "Varies by endpoint",
        "get_credentials_url": "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps",
    },
    "telegram": {
        "company": "Telegram FZ-LLC",
        "website": "https://telegram.org",
        "docs": "https://core.telegram.org/bots/api",
        "logo": "https://cdn.simpleicons.org/telegram",
        "color": "#26A5E4",
        "tagline": "Bot API for messaging and group management",
        "overview": "The Telegram Bot API lets you send and receive messages, manage groups and channels, handle inline queries, and create interactive bot experiences. Build notification bots, customer support flows, and command-driven automation.",
        "use_cases": ["Notification bots", "Group management", "Inline bot interactions", "Customer support", "Automated responses"],
        "auth_methods": ["Bot Token"],
        "pricing": "Free",
        "rate_limit": "30 messages/second (group), 1 msg/sec (per chat)",
        "get_credentials_url": "https://t.me/BotFather",
    },
    "trello": {
        "company": "Atlassian",
        "website": "https://trello.com",
        "docs": "https://developer.atlassian.com/cloud/trello/rest/api-group-actions/",
        "logo": "https://cdn.simpleicons.org/trello",
        "color": "#0052CC",
        "tagline": "Visual project management with boards and cards",
        "overview": "The Trello API provides access to boards, lists, cards, members, and labels. Create and organize Kanban workflows, manage task cards, track progress, and build custom project management integrations.",
        "use_cases": ["Kanban workflow management", "Task tracking", "Team collaboration", "Sprint boards", "Content planning"],
        "auth_methods": ["API Key + Token"],
        "pricing": "Free tier, Standard from $5/user/month",
        "rate_limit": "100 requests/10 seconds per token",
        "get_credentials_url": "https://trello.com/power-ups/admin",
    },
    "twilio": {
        "company": "Twilio Inc.",
        "website": "https://twilio.com",
        "docs": "https://www.twilio.com/docs/usage/api",
        "logo": "https://cdn.simpleicons.org/twilio",
        "color": "#F22F46",
        "tagline": "Communication APIs for SMS, voice, and video",
        "overview": "The Twilio API provides SMS messaging, voice calls, and communication services. Send and receive text messages, make and manage phone calls, verify phone numbers, and build multi-channel communication workflows.",
        "use_cases": ["SMS notifications", "Two-factor authentication", "Voice call automation", "Phone number verification", "WhatsApp messaging"],
        "auth_methods": ["Basic Auth (Account SID + Auth Token)"],
        "pricing": "Pay-per-use (SMS from $0.0079/msg)",
        "rate_limit": "Varies by service",
        "get_credentials_url": "https://console.twilio.com/",
    },
    "vercel": {
        "company": "Vercel Inc.",
        "website": "https://vercel.com",
        "docs": "https://vercel.com/docs/rest-api",
        "logo": "https://cdn.simpleicons.org/vercel",
        "color": "#000000",
        "tagline": "Frontend deployment and serverless platform",
        "overview": "The Vercel API provides access to projects, deployments, domains, and environment variables. Deploy applications, manage domains, configure environment settings, and automate your frontend CI/CD pipeline.",
        "use_cases": ["Deployment automation", "Domain management", "Environment variable management", "Project configuration", "Build monitoring"],
        "auth_methods": ["Bearer Token"],
        "pricing": "Free tier (Hobby), Pro from $20/user/month",
        "rate_limit": "Varies by endpoint",
        "get_credentials_url": "https://vercel.com/account/tokens",
    },
    "webhook": {
        "company": "ToolsConnector",
        "website": "https://github.com/sachinshelke/ToolsConnector",
        "docs": "https://github.com/sachinshelke/ToolsConnector",
        "logo": "",
        "color": "#6366F1",
        "tagline": "Send and manage HTTP webhooks to any endpoint",
        "overview": "The Webhook connector lets you send HTTP requests to any URL endpoint. Fire webhooks, manage retry logic, track delivery status, and build event-driven integrations with external services that accept webhooks.",
        "use_cases": ["Event notifications", "Service integration", "Custom API calls", "Webhook delivery with retry", "Cross-service triggers"],
        "auth_methods": ["Bearer Token", "API Key", "Custom Headers"],
        "pricing": "Free (built-in connector)",
        "rate_limit": "N/A (depends on target)",
        "get_credentials_url": "",
    },
    "zendesk": {
        "company": "Zendesk Inc.",
        "website": "https://zendesk.com",
        "docs": "https://developer.zendesk.com/api-reference/",
        "logo": "https://cdn.simpleicons.org/zendesk",
        "color": "#03363D",
        "tagline": "Customer service and support ticketing platform",
        "overview": "The Zendesk API provides access to tickets, users, organizations, and help center articles. Manage support workflows, automate ticket routing, track satisfaction scores, and build custom customer service integrations.",
        "use_cases": ["Ticket management", "Customer support automation", "Help center content", "Satisfaction tracking", "Multi-channel support"],
        "auth_methods": ["API Token", "OAuth 2.0"],
        "pricing": "Suite Team from $55/agent/month",
        "rate_limit": "400 requests/minute",
        "get_credentials_url": "https://developer.zendesk.com/documentation/ticketing/getting-started/getting-a-token/",
    },
}

# ── Category-based related connectors ──────────────────────────────────
_CATEGORY_RELATED: dict[str, list[tuple[str, str]]] = {
    "communication": [
        ("gmail", "Email automation"),
        ("slack", "Team messaging"),
        ("discord", "Community messaging"),
        ("teams", "Microsoft collaboration"),
        ("telegram", "Bot messaging"),
        ("outlook", "Microsoft email"),
        ("twilio", "SMS and voice"),
    ],
    "crm": [
        ("salesforce", "Enterprise CRM"),
        ("hubspot", "Marketing & sales CRM"),
        ("freshdesk", "Helpdesk"),
        ("intercom", "Customer messaging"),
        ("zendesk", "Support ticketing"),
    ],
    "project_management": [
        ("jira", "Issue tracking"),
        ("asana", "Work management"),
        ("linear", "Modern issue tracker"),
        ("trello", "Kanban boards"),
    ],
    "code_platform": [
        ("github", "Code hosting"),
        ("gitlab", "DevOps platform"),
    ],
    "devops": [
        ("cloudflare", "CDN and security"),
        ("datadog", "Monitoring"),
        ("pagerduty", "Incident management"),
        ("vercel", "Frontend deployment"),
        ("dockerhub", "Container registry"),
    ],
    "database": [
        ("airtable", "Spreadsheet database"),
        ("firestore", "Document database"),
        ("mongodb", "NoSQL database"),
        ("redis", "Key-value store"),
        ("supabase", "Postgres as a service"),
    ],
    "productivity": [
        ("gcalendar", "Calendar"),
        ("gdocs", "Documents"),
        ("gsheets", "Spreadsheets"),
        ("gtasks", "Task lists"),
        ("figma", "Design"),
        ("calendly", "Scheduling"),
        ("notion", "Workspace"),
    ],
    "ai_ml": [
        ("openai", "GPT models"),
        ("anthropic", "Claude models"),
        ("pinecone", "Vector database"),
    ],
    "finance": [
        ("stripe", "Payments"),
        ("plaid", "Banking data"),
    ],
    "marketing": [
        ("mailchimp", "Email marketing"),
        ("sendgrid", "Email delivery"),
    ],
    "storage": [
        ("gdrive", "Google storage"),
        ("s3", "AWS storage"),
    ],
    "message_queue": [
        ("rabbitmq", "Message broker"),
        ("sqs", "AWS queuing"),
    ],
    "analytics": [
        ("mixpanel", "Product analytics"),
        ("segment", "Customer data"),
    ],
    "security": [
        ("okta", "Identity management"),
        ("auth0", "Authentication"),
    ],
    "knowledge": [
        ("confluence", "Team wiki"),
        ("notion", "Knowledge workspace"),
    ],
    "ecommerce": [
        ("shopify", "E-commerce"),
        ("stripe", "Payments"),
    ],
    "custom": [
        ("webhook", "Custom webhooks"),
    ],
}


def _get_meta(name: str) -> dict:
    """Merge tool_metadata + EXTRA_META for a connector."""
    base = get_tool_meta(name)
    if name in EXTRA_META:
        # Fill only missing keys
        for k, v in EXTRA_META[name].items():
            if not base.get(k):
                base[k] = v
    return base


def _get_related(name: str, category: str) -> list[tuple[str, str, str]]:
    """Return up to 4 related connectors as (name, display, reason) tuples."""
    related = _CATEGORY_RELATED.get(category, [])
    result = []
    for rname, reason in related:
        if rname != name and len(result) < 4:
            result.append((rname, rname.replace("_", " ").title(), reason))
    return result


def _protocol_label(proto: str) -> str:
    if proto.lower() == "graphql":
        return "GraphQL"
    return proto.upper()


def _generate_readme(name: str, sp: dict, meta: dict) -> str:
    """Generate a complete README.md for a connector."""
    display = sp.get("display_name", name.title())
    desc = meta.get("tagline") or sp.get("description", "")
    company = meta.get("company", "")
    category = sp.get("category", "").replace("_", " ").title()
    protocol = _protocol_label(sp.get("protocol", "rest"))
    website = meta.get("website", "")
    docs = meta.get("docs", "")
    auth = ", ".join(meta.get("auth_methods", [])) or "Bearer Token"
    rate_limit = meta.get("rate_limit", "See API documentation")
    pricing = meta.get("pricing", "See website")
    overview = meta.get("overview", desc)
    use_cases = meta.get("use_cases", [])
    cred_url = meta.get("get_credentials_url", "")
    cred_steps = meta.get("get_credentials_steps", "")

    actions = sp.get("actions", {})
    # Pick best first action for quickstart
    first_action = _best_first_action(actions, name)

    # Build the README
    lines = []

    # Header
    lines.append(f"# {display}\n")
    lines.append(f"> {desc}\n")

    # Info table
    lines.append("| | |")
    lines.append("|---|---|")
    if company:
        lines.append(f"| **Company** | {company} |")
    lines.append(f"| **Category** | {category} |")
    lines.append(f"| **Protocol** | {protocol} |")
    if website:
        domain = website.replace("https://", "").replace("http://", "").rstrip("/")
        lines.append(f"| **Website** | [{domain}]({website}) |")
    if docs:
        docs_domain = docs.replace("https://", "").replace("http://", "").split("/")[0]
        lines.append(f"| **API Docs** | [{docs_domain}]({docs}) |")
    lines.append(f"| **Auth** | {auth} |")
    lines.append(f"| **Rate Limit** | {rate_limit} |")
    lines.append(f"| **Pricing** | {pricing} |")
    lines.append("")
    lines.append("---\n")

    # Overview
    lines.append("## Overview\n")
    lines.append(f"{overview}\n")

    # Use Cases
    if use_cases:
        lines.append("## Use Cases\n")
        for uc in use_cases:
            lines.append(f"- {uc}")
        lines.append("")

    # Installation
    lines.append("## Installation\n")
    lines.append("```bash")
    lines.append(f"pip install toolsconnector[{name}]")
    lines.append("```\n")
    lines.append("Set your credentials:\n")
    lines.append("```bash")
    lines.append(f"export TC_{name.upper()}_CREDENTIALS=your-token")
    lines.append("```\n")

    # Quick Start
    lines.append("## Quick Start\n")
    lines.append("```python")
    lines.append("from toolsconnector.serve import ToolKit\n")
    lines.append(f'kit = ToolKit(["{name}"], credentials={{"{name}": "your-token"}})\n')

    # Generate a realistic quickstart example
    if first_action and first_action in actions:
        act = actions[first_action]
        params = act.get("parameters", [])
        req_params = [p for p in params if p.get("required")]
        opt_params = [p for p in params if not p.get("required")]
        ex_params = req_params + opt_params[:2]
        if ex_params:
            args = ", ".join(f'"{p["name"]}": {_example_value(p)}' for p in ex_params)
            lines.append(f'# {act.get("description", first_action)}')
            lines.append(f'result = kit.execute("{name}_{first_action}", {{{args}}})')
        else:
            lines.append(f'# {act.get("description", first_action)}')
            lines.append(f'result = kit.execute("{name}_{first_action}", {{}})')
    else:
        lines.append(f'result = kit.execute("{name}_action", {{}})')
    lines.append("print(result)")
    lines.append("```\n")

    # MCP + OpenAI
    lines.append("### MCP Server\n")
    lines.append("```python")
    lines.append(f'kit = ToolKit(["{name}"], credentials={{"{name}": "your-token"}})')
    lines.append("kit.serve_mcp()  # Claude Desktop / Cursor connects instantly")
    lines.append("```\n")

    lines.append("### OpenAI Function Calling\n")
    lines.append("```python")
    lines.append(f'kit = ToolKit(["{name}"], credentials={{"{name}": "your-token"}})')
    lines.append("tools = kit.to_openai_tools()")
    lines.append("# Pass to: openai.chat.completions.create(tools=tools, ...)")
    lines.append("```\n")

    # Authentication
    lines.append("## Authentication\n")
    auth_methods = meta.get("auth_methods", []) or ["Bearer Token"]
    lines.append(f"### {auth_methods[0]}\n")
    if cred_steps:
        for i, step in enumerate(cred_steps.split(" > "), 1):
            lines.append(f"{i}. {step.strip()}")
    else:
        lines.append(f"1. Create an account at [{display}]({website})" if website else "1. Create an account")
        lines.append("2. Navigate to API settings or developer console")
        lines.append("3. Generate an API key or access token")
    lines.append("")
    if cred_url:
        lines.append(f"[Get credentials &rarr;]({cred_url})\n")

    # Error Handling
    lines.append("## Error Handling\n")
    lines.append("```python")
    lines.append("from toolsconnector.errors import RateLimitError, AuthError\n")
    lines.append("try:")
    if first_action:
        lines.append(f'    result = kit.execute("{name}_{first_action}", {{}})')
    else:
        lines.append(f'    result = kit.execute("{name}_action", {{}})')
    lines.append("except RateLimitError as e:")
    lines.append('    print(f"Rate limited. Retry in {e.retry_after_seconds}s")')
    lines.append("except AuthError as e:")
    lines.append('    print(f"Auth failed: {e.suggestion}")')
    lines.append("```\n")

    # Actions (auto-generated marker)
    lines.append("## Actions\n")
    lines.append("<!-- ACTIONS_START -->")
    lines.append("<!-- This section is auto-generated from the connector spec. Do not edit manually. -->")
    lines.append("<!-- ACTIONS_END -->\n")

    # Tips
    lines.append("## Tips\n")
    tips = _generate_tips(name, actions, meta)
    for tip in tips:
        lines.append(f"- {tip}")
    lines.append("")

    # Related
    related = _get_related(name, sp.get("category", ""))
    if related:
        lines.append("## Related Connectors\n")
        for rname, rdisplay, reason in related:
            lines.append(f"- [{rdisplay}](../{rname}/) — {reason}")
        lines.append("")

    lines.append("---\n")
    lines.append("*This connector is part of [ToolsConnector](https://github.com/sachinshelke/ToolsConnector) — the universal tool-connection primitive for Python and AI agents.*")
    lines.append("")

    return "\n".join(lines)


def _best_first_action(actions: dict, connector_name: str) -> str:
    """Pick the most useful action for quickstart."""
    preferred = [
        "list_emails", "list_messages", "list_files", "list_events",
        "list_repos", "list_channels", "list_contacts", "list_issues",
        "list_records", "list_tasks", "list_products", "list_projects",
        "list_tickets", "list_users", "list_boards", "list_cards",
        "list_pages", "list_databases", "list_incidents", "list_queues",
        "list_deployments", "list_vectors",
        "get_values", "get_spreadsheet", "get_document",
        "search", "query", "send_message",
    ]
    for name in preferred:
        if name in actions:
            return name
    for aname in sorted(actions.keys()):
        if aname.startswith("list_") or aname.startswith("get_"):
            return aname
    return sorted(actions.keys())[0] if actions else ""


def _example_value(p: dict) -> str:
    """Generate a realistic example value for a parameter."""
    ptype = p.get("type", "string")
    pname = p.get("name", "value")
    if p.get("default") is not None:
        v = p["default"]
        if isinstance(v, str):
            return f'"{v}"'
        if isinstance(v, bool):
            return "True" if v else "False"
        return str(v)
    if ptype == "boolean":
        return "True"
    if ptype in ("integer", "number"):
        # Contextual defaults
        if "limit" in pname or "max" in pname or "count" in pname:
            return "10"
        if "page" in pname:
            return "1"
        return "10"
    # String contextual examples
    examples = {
        "query": '"is:unread"', "q": '"search term"',
        "email": '"user@example.com"', "to": '"recipient@example.com"',
        "subject": '"Hello from ToolsConnector"',
        "body": '"Hello! Sent via ToolsConnector."',
        "channel": '"general"', "channel_id": '"C01234567"',
        "team_id": '"T01234567"', "workspace_id": '"ws-123"',
        "project_id": '"proj-123"', "project": '"my-project"',
        "repo": '"owner/repo"', "owner": '"owner"',
        "title": '"My Title"', "name": '"my-name"',
        "description": '"A description"',
        "status": '"active"', "state": '"open"',
        "key": '"my-key"', "value": '"my-value"',
        "message": '"Hello!"', "text": '"Hello!"',
        "url": '"https://example.com"',
        "path": '"/path/to/file"',
        "domain": '"example.com"',
        "bucket": '"my-bucket"',
        "collection": '"my-collection"',
        "database": '"my-database"', "database_id": '"db-123"',
        "index_name": '"my-index"', "namespace": '"default"',
        "user_id": '"user-123"', "contact_id": '"contact-123"',
        "ticket_id": '"ticket-123"', "issue_id": '"issue-123"',
        "board_id": '"board-123"', "card_id": '"card-123"',
        "page_id": '"page-123"', "space_id": '"space-123"',
        "file_id": '"file-123"', "document_id": '"doc-123"',
        "spreadsheet_id": '"sheet-123"',
        "calendar_id": '"primary"',
        "list_id": '"list-123"', "task_id": '"task-123"',
        "campaign_id": '"campaign-123"',
        "template_id": '"template-123"',
        "queue_url": '"https://sqs.region.amazonaws.com/123/queue"',
    }
    return examples.get(pname, f'"your-{pname}"')


def _generate_tips(name: str, actions: dict, meta: dict) -> list[str]:
    """Generate useful tips for a connector."""
    tips = []
    action_names = sorted(actions.keys())
    act_count = len(action_names)

    # Tip about batch operations
    batch_actions = [a for a in action_names if "batch" in a]
    if batch_actions:
        tips.append(f"Use batch operations ({', '.join(f'`{a}`' for a in batch_actions[:3])}) for bulk operations instead of individual calls")

    # Tip about list vs search
    list_actions = [a for a in action_names if a.startswith("list_")]
    search_actions = [a for a in action_names if a.startswith("search_") or a == "search"]
    if list_actions and search_actions:
        tips.append(f"Use `{search_actions[0]}` for filtered queries and `{list_actions[0]}` for paginated browsing")

    # Tip about rate limits
    rate = meta.get("rate_limit", "")
    if rate:
        tips.append(f"Rate limit is {rate} — use pagination and caching to minimize API calls")

    # Tip about dangerous actions
    dangerous = [a for a in action_names if actions[a].get("dangerous")]
    if dangerous:
        tips.append(f"Actions marked as destructive ({', '.join(f'`{a}`' for a in dangerous[:3])}) cannot be undone — use with caution")

    # Tip about pagination
    if any("cursor" in str(actions[a].get("parameters", [])) for a in action_names):
        tips.append("Use cursor-based pagination for large result sets — pass the `cursor` from previous responses")

    # Generic useful tips
    if act_count > 20:
        tips.append(f"This connector has {act_count} actions — use `ToolKit(include_actions=[...])` to expose only what your agent needs")

    if not tips:
        tips = [
            "Always handle `RateLimitError` and implement exponential backoff for production use",
            "Use `ToolKit.aexecute()` for async workflows to avoid blocking",
            f"Check the {meta.get('docs', 'API docs')} for field-level documentation and edge cases",
        ]

    return tips[:4]


def main():
    connectors_dir = ROOT / "src" / "toolsconnector" / "connectors"
    generated = 0
    skipped = 0

    for name in sorted(list_connectors()):
        readme_path = connectors_dir / name / "README.md"

        if readme_path.exists():
            print(f"  SKIP  {name} (already has README.md)")
            skipped += 1
            continue

        # Make sure the directory exists
        if not (connectors_dir / name).is_dir():
            print(f"  SKIP  {name} (no directory)")
            skipped += 1
            continue

        try:
            sp = extract_spec(name)
            meta = _get_meta(name)
            content = _generate_readme(name, sp, meta)
            readme_path.write_text(content, encoding="utf-8")
            act_count = len(sp.get("actions", {}))
            print(f"  DONE  {name} ({act_count} actions)")
            generated += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")

    print(f"\nGenerated: {generated} | Skipped: {skipped}")


if __name__ == "__main__":
    main()
