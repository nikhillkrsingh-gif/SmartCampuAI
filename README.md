# 🎓 SmartCampus AI — Intelligent Campus Assistant & RAG Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Framework-Flask-black.svg)](https://flask.palletsprojects.com/)
[![Inference](https://img.shields.io/badge/AI_Engine-Groq_Cloud-orange.svg)](https://groq.com/)
[![Database](https://img.shields.io/badge/Database-SQLite3-green.svg)](https://www.sqlite.org/)
[![Deployment](https://img.shields.io/badge/Deploy-Render-46E3B7.svg)](https://render.com/)

SmartCampus AI is an institutional intelligence assistant built by **Team FutureMind**. It provides contextual, accurate answers to student and faculty inquiries by training directly on official institutional files—such as hackathon rosters, exam schedules, circulars, and campus guidelines—using Retrieval-Augmented Generation (RAG).

---

## 🌟 Core Highlights

- **Document-First AI Knowledge Engine (RAG):** The AI does not guess or hallucinate. It is grounded on uploaded campus records (PDF, DOCX, CSV) and extracts relevant sections before formulating answers, citing verified facts with `(Official Campus Record)`.
- **Live 2-Step Student ID Enrollment (Gmail OTP):** When creating a student account, the platform enforces email verification by dispatching a live 6-digit OTP code to the student's Gmail via authenticated TLS SMTP.
- **Simplified Everyday Sign-In:** Once registered and verified, students, faculty, and administrators log in using only their **Username** and **Password** without recurring OTP friction.
- **Role-Based Access Control (RBAC):** Distinct permissions and dashboards for **Students**, **Faculty**, and **Administrators**, including document management and faculty ID generation.
- **Multi-Thread Workspace:** Full chat session history with dynamic topic labeling, per-thread deletion (`DEL`), and table rendering via Marked.js.
- **Cloud-Optimized Architecture:** Lightweight dependency configuration engineered to deploy to Render within 2 minutes without exceeding memory limits.

---

## 🧠 Architecture: Document-First AI Pipeline

The system ensures answers reflect official records through an automated extraction and vector retrieval pipeline:

