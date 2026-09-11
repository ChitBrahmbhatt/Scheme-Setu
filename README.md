# AI-Driven Scheme Matching for Marginalized Entrepreneurs

An AI-powered platform that helps marginalized and underserved entrepreneurs discover **relevant government schemes, subsidies, financial assistance, and support programs** based on their individual profile, business requirements, and eligibility criteria.

## 🚀 Overview

Finding the right government scheme can be difficult because information is often spread across multiple portals, eligibility conditions can be complex, and entrepreneurs may not know which schemes apply to them.

This project aims to simplify that process using **Artificial Intelligence and intelligent scheme matching**.

The system analyzes an entrepreneur's profile and requirements and recommends the most relevant government schemes along with their eligibility, benefits, and application information.

## 🎯 Problem Statement

Marginalized entrepreneurs often face difficulties in accessing government support due to:

* Lack of awareness about available schemes
* Complex eligibility criteria
* Information scattered across different government portals
* Difficulty identifying schemes relevant to their specific situation
* Language and accessibility barriers
* Time-consuming manual scheme discovery

## 💡 Proposed Solution

Our platform provides a centralized and intelligent scheme-discovery system.

Users provide information such as:

* Entrepreneur profile
* Business type
* Location
* Category
* Business stage
* Funding requirements
* Sector/industry
* Other relevant eligibility information

The AI system processes this information and generates a ranked list of potentially relevant schemes.

### Key Features

* 🤖 **AI-Based Scheme Matching**
* 🎯 **Personalized Recommendations**
* 📋 **Eligibility Analysis**
* 💰 **Scheme Benefit Information**
* 🔎 **Intelligent Search and Filtering**
* 📊 **Scheme Comparison**
* 👤 **User Profile-Based Matching**
* 🌐 **Accessible and User-Friendly Interface**
* 📱 **Responsive Frontend**
* 🔐 **Secure Backend Architecture**

## 🏗️ System Architecture

```text
                    ┌─────────────────────┐
                    │       User          │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      Frontend       │
                    │   Web Application   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       Backend       │
                    │      REST API       │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
        ┌────────────┐ ┌─────────────┐ ┌──────────────┐
        │ User Data  │ │ Scheme Data  │ │ AI Matching  │
        │            │ │             │ │    Engine    │
        └────────────┘ └─────────────┘ └──────┬───────┘
                                              │
                                              ▼
                                   ┌────────────────────┐
                                   │ Ranked Scheme      │
                                   │ Recommendations    │
                                   └────────────────────┘
```

## 🛠️ Technology Stack

### Frontend

* HTML
* CSS
* JavaScript
* [Add your frontend framework here if applicable]

### Backend

* Python
* FastAPI
* Uvicorn

### AI / Machine Learning

* [Add model / NLP technology used]
* [Add embedding/vector database if applicable]
* [Add matching/ranking approach]

### Database

* [Add database used]

### Development Tools

* Git
* GitHub
* VS Code
* Python Virtual Environment

## 📂 Project Structure

```text
.
├── frontend/
│   ├── ...
│   └── ...
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   └── ...
│   └── ...
│
├── data/
│   └── ...
│
├── requirements.txt
├── .gitignore
├── README.md
└── ...
```

> The exact structure may vary depending on the current implementation.

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
```

### 3. Activate the virtual environment

#### macOS / Linux

```bash
source .venv/bin/activate
```

#### Windows

```bash
.venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

The backend will normally be available at:

```text
http://127.0.0.1:8000
```

## 🌐 Running the Frontend

Open the frontend application according to the project's frontend setup.

If the project uses a simple HTML/JavaScript frontend, you can run it using a local development server.

For example:

```bash
python3 -m http.server 5500
```

Then open:

```text
http://localhost:5500
```

## 🔄 How It Works

### Step 1 — User Profile

The entrepreneur enters their relevant personal and business information.

### Step 2 — Requirement Analysis

The system identifies important attributes such as business sector, location, category, funding needs, and other eligibility factors.

### Step 3 — Scheme Matching

The AI/matching engine compares the user's profile with available government schemes.

### Step 4 — Ranking

Potentially relevant schemes are ranked based on their suitability and eligibility.

### Step 5 — Recommendations

The user receives a personalized list of schemes with relevant information such as:

* Scheme name
* Eligibility
* Benefits
* Financial assistance
* Required documents
* Application information

## 📊 Example User Flow

```text
User
  │
  ▼
Enter Profile
  │
  ▼
Enter Business Requirements
  │
  ▼
AI Processes Information
  │
  ▼
Match Against Schemes
  │
  ▼
Calculate Relevance
  │
  ▼
Rank Schemes
  │
  ▼
Personalized Recommendations
```

## 🔐 Security & Privacy

The application is designed with user data privacy and security in mind.

Important practices include:

* Environment variables for sensitive configuration
* No API keys committed to GitHub
* `.env` files excluded using `.gitignore`
* Input validation
* Secure backend communication
* Minimal collection of user information

**Never commit API keys, passwords, database credentials, or other secrets to the repository.**

## 🧪 Testing

Testing should cover:

* User registration/profile inputs
* Scheme eligibility matching
* API endpoints
* Recommendation accuracy
* Frontend functionality
* Invalid input handling
* Edge cases

## 📈 Future Scope

Potential future improvements include:

* Multilingual support
* Voice-based interaction
* Improved AI recommendation models
* Integration with official government APIs
* Automated scheme updates
* Document-based eligibility verification
* Application-status tracking
* Personalized notifications
* Mobile application
* Explainable AI recommendations

## 👥 Team

Developed as part of **Smart India Hackathon (SIH) 2026**.

**Project:** AI-Driven Scheme Matching for Marginalized Entrepreneurs

## 📜 Disclaimer

The recommendations provided by this platform are intended to assist users in discovering potentially relevant government schemes.

Users should verify the latest eligibility requirements, benefits, deadlines, and application procedures through the respective official government sources before applying.

## ⭐ Contributing

Contributions, suggestions, and improvements are welcome.

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/your-feature
```

3. Commit your changes

```bash
git commit -m "Add your feature"
```

4. Push the branch

```bash
git push origin feature/your-feature
```

5. Open a Pull Request

## 📄 License

This project is currently developed for **Smart India Hackathon 2026**.

Add the appropriate license here if your team decides to release the project under an open-source license.
