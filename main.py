import streamlit as st
from streamlit_javascript import st_javascript
import pymongo
from pymongo import MongoClient
import uuid
import random
import pandas as pd
import os
import altair as alt
from textblob import TextBlob
import numpy as np
from datetime import datetime, timedelta
import time
from PIL import Image
import base64
from itertools import combinations

# 🛠️ Configuration de la page
st.set_page_config(
    page_title="Wiki Survey - Afrique",
    layout="wide",
    page_icon="🗳️",
    initial_sidebar_state="collapsed"
)

# === Configuration MongoDB ===
MONGO_URI = "mongodb://mongo:WGLPiIcYKLnGksuHaBpVJNcJjwCpURei@metro.proxy.rlwy.net:14731"
DB_NAME = "Africas"

# Variable globale pour marquer l'initialisation
_db_initialized = False

# --- Connexion à MongoDB ---
@st.cache_resource
def get_db_connection():
    """Obtenir une connexion à MongoDB"""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Tester la connexion
        client.server_info()
        db = client[DB_NAME]
        print("✅ Connexion MongoDB réussie")
        return db
    except Exception as e:
        print(f"❌ Erreur de connexion à MongoDB: {e}")
        st.error(f"Erreur de connexion à MongoDB: {e}")
        return None

# === Création des collections et index ===
def init_database():
    """Initialiser la structure de la base MongoDB"""
    global _db_initialized
    
    # Éviter les réinitialisations multiples
    if _db_initialized:
        print("⚠️ Base déjà initialisée (skip)")
        return True
    
    try:
        db = get_db_connection()
        
        if db is None:
            print("❌ Impossible d'initialiser : pas de connexion DB")
            return False
        
        # Vérifier si déjà initialisé via une collection système
        try:
            system_init = db.system_initialized.find_one({"_id": "app_init"})
            if system_init and system_init.get("init"):
                print("✅ Base déjà initialisée (via système)")
                _db_initialized = True
                return True
        except Exception as e:
            print(f"Vérification initialisation : {e}")
        
        # Créer les collections si elles n'existent pas
        collections = [
            "navigateur", "login", "question",
            "idees", "vote", "commentaire",
            "profil", "sentiment_analytics"
        ]

        existing_collections = db.list_collection_names()
        
        for collection in collections:
            if collection not in existing_collections:
                db.create_collection(collection)
                print(f"✅ Collection '{collection}' créée")

        # Créer les index (avec gestion d'erreurs)
        try:
            db.login.create_index("email", unique=True)
            db.idees.create_index("id_question")
            db.vote.create_index([("id_navigateur", 1), ("id_question", 1)])
            db.profil.create_index("id_navigateur", unique=True)
            db.sentiment_analytics.create_index("id_question", unique=True)
            print("✅ Index créés")
        except Exception as e:
            print(f"⚠️ Certains index existent déjà : {e}")

        # Insérer des données de test
        try:
            db.login.update_one(
                {"email": "admin@test.com"},
                {"$set": {
                    "email": "admin@test.com",
                    "mot_de_passe": "admin123",
                    "date_creation": datetime.now()
                }},
                upsert=True
            )
            
            db.login.update_one(
                {"email": "yinnaasome@gmail.com"},
                {"$set": {
                    "email": "yinnaasome@gmail.com",
                    "mot_de_passe": "abc",
                    "date_creation": datetime.now()
                }},
                upsert=True
            )
            print("✅ Utilisateurs par défaut créés")
        except Exception as e:
            print(f"⚠️ Erreur création utilisateurs : {e}")
        
        # Marquer comme initialisé
        try:
            db.system_initialized.update_one(
                {"_id": "app_init"},
                {"$set": {"init": True, "date": datetime.now()}},
                upsert=True
            )
            print("✅ Marqué comme initialisé")
        except Exception as e:
            print(f"⚠️ Erreur marquage initialisation : {e}")
        
        _db_initialized = True
        print("✅ Base MongoDB initialisée avec succès")
        return True
        
    except Exception as e:
        print(f"❌ Erreur initialisation MongoDB: {e}")
        import traceback
        traceback.print_exc()
        return False

# === Analyse de sentiment ===
def analyze_sentiment(text):
    """Analyser le sentiment d'un texte avec TextBlob"""
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity

        if polarity > 0.1:
            label = "Positif"
        elif polarity < -0.1:
            label = "Négatif"
        else:
            label = "Neutre"

        return polarity, label
    except:
        return 0.0, "Neutre"

def update_sentiment_analytics(question_id):
    """Mettre à jour les analytics de sentiment pour une question"""
    try:
        db = get_db_connection()
        
        if db is None:
            return

        # Calculer les stats pour les idées
        idees_stats_cursor = db.idees.aggregate([
            {"$match": {"id_question": question_id}},
            {"$group": {
                "_id": None,
                "avg_sentiment": {"$avg": "$sentiment_score"},
                "positifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Positif"]}, 1, 0]}},
                "negatifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Négatif"]}, 1, 0]}},
                "neutres": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Neutre"]}, 1, 0]}}
            }}
        ])
        idees_stats = next(idees_stats_cursor, {})

        # Calculer les stats pour les commentaires
        commentaires_stats_cursor = db.commentaire.aggregate([
            {"$match": {"id_question": question_id}},
            {"$group": {
                "_id": None,
                "avg_sentiment": {"$avg": "$sentiment_score"},
                "positifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Positif"]}, 1, 0]}},
                "negatifs": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Négatif"]}, 1, 0]}},
                "neutres": {"$sum": {"$cond": [{"$eq": ["$sentiment_label", "Neutre"]}, 1, 0]}}
            }}
        ])
        commentaires_stats = next(commentaires_stats_cursor, {})

        # Insérer ou mettre à jour les analytics
        db.sentiment_analytics.update_one(
            {"id_question": question_id},
            {"$set": {
                "moyenne_sentiment_idees": idees_stats.get("avg_sentiment", 0),
                "moyenne_sentiment_commentaires": commentaires_stats.get("avg_sentiment", 0),
                "total_idees_positives": idees_stats.get("positifs", 0),
                "total_idees_negatives": idees_stats.get("negatifs", 0),
                "total_idees_neutres": idees_stats.get("neutres", 0),
                "total_commentaires_positifs": commentaires_stats.get("positifs", 0),
                "total_commentaires_negatifs": commentaires_stats.get("negatifs", 0),
                "total_commentaires_neutres": commentaires_stats.get("neutres", 0),
                "derniere_mise_a_jour": datetime.now()
            }},
            upsert=True
        )

    except Exception as e:
        st.error(f"Erreur mise à jour analytics: {e}")

# Initialisation de la base avec gestion d'erreur
try:
    if not init_database():
        st.error("⚠️ Avertissement : Erreur lors de l'initialisation de la base de données. Certaines fonctionnalités peuvent ne pas fonctionner.")
except Exception as e:
    st.error(f"⚠️ Erreur critique lors de l'initialisation : {e}")
    print(f"❌ Erreur critique : {e}")

# Initialiser les clés nécessaires dans session_state
if "page" not in st.session_state:
    st.session_state["page"] = "home"

if "id_navigateur" not in st.session_state:
    st.session_state["id_navigateur"] = None

if "auth" not in st.session_state:
    st.session_state.auth = False

if "utilisateur_id" not in st.session_state:
    st.session_state.utilisateur_id = None

if "email" not in st.session_state:
    st.session_state.email = None

if "current_tab" not in st.session_state:
    st.session_state.current_tab = "home"

# --- ID navigateur ---
def get_navigateur_id():
    try:
        js_code = """
            const existing = localStorage.getItem("id_navigateur");
            if (existing) {
                existing;
            } else {
                const newId = crypto.randomUUID();
                localStorage.setItem("id_navigateur", newId);
                newId;
            }
        """
        return st_javascript(js_code)
    except:
        # Fallback si JavaScript ne fonctionne pas
        return str(uuid.uuid4())

def detect_navigateur():
    try:
        js_code = "navigator.userAgent;"
        agent = st_javascript(js_code)
        if agent:
            if "Chrome" in agent and "Edg" not in agent:
                return "Chrome"
            elif "Firefox" in agent:
                return "Firefox"
            elif "Edg" in agent:
                return "Edge"
            elif "Safari" in agent and "Chrome" not in agent:
                return "Safari"
    except:
        pass
    return "Inconnu"

def init_navigateur():
    if not st.session_state["id_navigateur"]:
        id_navigateur = get_navigateur_id()
        if id_navigateur and len(str(id_navigateur)) > 100:
            id_navigateur = str(id_navigateur)[:100]
        
        navigateur_nom = detect_navigateur()
        
        if id_navigateur:
            st.session_state["id_navigateur"] = id_navigateur
            try:
                db = get_db_connection()
                if db:
                    db.navigateur.update_one(
                        {"id_navigateur": id_navigateur},
                        {"$set": {
                            "id_navigateur": id_navigateur,
                            "navigateur": navigateur_nom,
                            "date_creation": datetime.now()
                        }},
                        upsert=True
                    )
            except Exception as e:
                print(f"Erreur enregistrement navigateur : {e}")

# Appel obligatoire
init_navigateur()

# =============================================================
# === FONCTIONS D'AUTHENTIFICATION ===
# =============================================================

def creer_compte():
    """Page de création de compte pour les nouveaux utilisateurs."""
    st.subheader("Créez votre compte pour proposer une question")
    db = get_db_connection()
    
    if db is None:
        st.error("Impossible de se connecter à la base de données")
        return

    email_reg = st.text_input("Email", key="email_reg")
    mot_de_passe_reg = st.text_input("Mot de passe", type="password", key="pass_reg")
    mot_de_passe_conf = st.text_input("Confirmer le mot de passe", type="password", key="pass_conf")

    if st.button("Créer le compte", key="btn_creer_compte"):
        if not email_reg or not mot_de_passe_reg or not mot_de_passe_conf:
            st.error("Veuillez remplir tous les champs.")
            return

        if mot_de_passe_reg != mot_de_passe_conf:
            st.error("Les mots de passe ne correspondent pas.")
            return

        # Vérifier si l'email existe déjà
        if db.login.find_one({"email": email_reg}):
            st.error("Cet email est déjà utilisé. Veuillez vous connecter.")
            return

        # Enregistrer le nouvel utilisateur
        nouvel_utilisateur = {
            "email": email_reg,
            "mot_de_passe": mot_de_passe_reg,
            "date_creation": datetime.now()
        }
        user_id = db.login.insert_one(nouvel_utilisateur).inserted_id

        # Connexion automatique après la création
        st.session_state.auth = True
        st.session_state.utilisateur_id = str(user_id)
        st.session_state.email = email_reg
        st.success(f"✅ Compte créé et connexion réussie ! Bienvenue {st.session_state.email} !")
        time.sleep(1)
        st.rerun()

def login_page():
    """Interface de connexion pour les utilisateurs existants."""
    st.subheader("Connectez-vous pour proposer une question")
    db = get_db_connection()
    
    if db is None:
        st.error("Impossible de se connecter à la base de données")
        return
        
    email = st.text_input("Email", key="email_login")
    mot_de_passe = st.text_input("Mot de passe", type="password", key="pass_login")

    if st.button("Se connecter", key="btn_login"):
        utilisateur = db.login.find_one({
            "email": email,
            "mot_de_passe": mot_de_passe
        })

        if utilisateur:
            st.session_state.auth = True
            st.session_state.utilisateur_id = str(utilisateur["_id"])
            st.session_state.email = utilisateur["email"]
            st.success(f"✅ Bienvenue {st.session_state.email} !")
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ Identifiants incorrects")

def authentication_flow():
    """Gère la connexion et la création de compte via des onglets"""
    tab_login, tab_register = st.tabs(["🔒 Se connecter", "✍️ Créer un compte"])

    with tab_login:
        login_page()

    with tab_register:
        creer_compte()

# =============================================================
# === FONCTIONS PRINCIPALES ===
# =============================================================

def creer_question():
    st.header("✍️ Créer une nouvelle question")

    # Vérifier si l'utilisateur est connecté
    if not st.session_state.get("auth"):
        st.info("Veuillez vous connecter ou créer un compte pour proposer une question.")
        authentication_flow()
        return

    with st.form("form_question"):
        question = st.text_input("Votre question :", 
                               placeholder="Ex: Quelle est la priorité pour le développement de l'Afrique ?")
        idee1 = st.text_input("Idée 1 :", 
                            placeholder="Ex: Éducation gratuite pour tous")
        idee2 = st.text_input("Idée 2 :", 
                            placeholder="Ex: Monnaie unique africaine")
        
        submitted = st.form_submit_button("Créer la question")

        if submitted:
            if not question.strip():
                st.error("Veuillez saisir une question.")
                return
            if not idee1.strip() or not idee2.strip():
                st.error("Veuillez saisir deux idées pour la question.")
                return

            db = get_db_connection()
            
            if db is None:
                st.error("Impossible de se connecter à la base de données")
                return

            # Insérer la question
            question_data = {
                "question": question.strip(),
                "createur_id": st.session_state.utilisateur_id,
                "createur_email": st.session_state.email,
                "date_creation": datetime.now()
            }
            question_id = db.question.insert_one(question_data).inserted_id

            # Analyser sentiment des idées
            score1, label1 = analyze_sentiment(idee1)
            score2, label2 = analyze_sentiment(idee2)

            # Insérer les idées
            db.idees.insert_many([
                {
                    "id_question": question_id,
                    "idee_texte": idee1.strip(),
                    "creer_par_utilisateur": "non",
                    "date_creation": datetime.now(),
                    "sentiment_score": float(score1),
                    "sentiment_label": label1
                },
                {
                    "id_question": question_id,
                    "idee_texte": idee2.strip(),
                    "creer_par_utilisateur": "non",
                    "date_creation": datetime.now(),
                    "sentiment_score": float(score2),
                    "sentiment_label": label2
                }
            ])

            # Mettre à jour les analytics
            update_sentiment_analytics(question_id)

            st.success("✅ Question et idées enregistrées avec succès !")
            st.balloons()
            time.sleep(2)
            st.rerun()

def get_vote_pairs(question_id, id_navigateur):
    """Obtenir toutes les paires d'idées non votées pour une question"""
    db = get_db_connection()
    
    if db is None:
        return []
    
    # Récupérer toutes les idées pour cette question
    all_ideas = list(db.idees.find(
        {"id_question": question_id}, 
        {"_id": 1, "idee_texte": 1, "creer_par_utilisateur": 1}
    ))
    
    if len(all_ideas) < 2:
        return []
    
    # Générer toutes les combinaisons possibles de paires
    all_pairs = list(combinations(all_ideas, 2))
    
    # Récupérer les paires déjà votées par cet utilisateur
    user_votes = list(db.vote.find(
        {
            "id_navigateur": id_navigateur,
            "id_question": question_id
        },
        {"id_idee_gagnant": 1, "id_idee_perdant": 1}
    ))
    
    # Convertir en ensemble de tuples (id1, id2) pour comparaison rapide
    voted_pairs = set()
    for vote in user_votes:
        pair = tuple(sorted([vote["id_idee_gagnant"], vote["id_idee_perdant"]]))
        voted_pairs.add(pair)
    
    # Filtrer les paires non votées
    available_pairs = []
    for idea1, idea2 in all_pairs:
        pair_ids = tuple(sorted([idea1["_id"], idea2["_id"]]))
        if pair_ids not in voted_pairs:
            available_pairs.append((idea1, idea2))
    
    return available_pairs

def participer():
    """Interface de participation au vote avec logique Salganik corrigée"""
    st.header("🗳️ Participer aux votes")
    
    db = get_db_connection()
    
    if db is None:
        st.error("Impossible de se connecter à la base de données")
        return

    # Récupérer toutes les questions
    all_questions = list(db.question.find({}, {"_id": 1, "question": 1, "date_creation": 1}).sort("date_creation", -1))

    if not all_questions:
        st.info("Aucune question disponible pour le moment.")
        return

    # Vérifier quelles questions ont encore des paires non votées
    questions_with_available_pairs = []
    for question in all_questions:
        available_pairs = get_vote_pairs(question["_id"], st.session_state.id_navigateur)
        if available_pairs:
            questions_with_available_pairs.append({
                "question": question,
                "available_pairs": len(available_pairs)
            })

    if not questions_with_available_pairs:
        st.success("🎉 Vous avez voté sur toutes les paires disponibles !")
        st.info("💡 De nouvelles idées ou questions apparaîtront ici lorsqu'elles seront créées.")
        afficher_formulaire_profil()
        return

    # Initialiser les variables de session pour cette page
    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0
    
    if 'current_pair_index' not in st.session_state:
        st.session_state.current_pair_index = 0
    
    if 'current_question_id' not in st.session_state:
        st.session_state.current_question_id = questions_with_available_pairs[0]["question"]["_id"]

    # Sélection de la question
    selected_question = None
    selected_question_data = None
    
    for i, q_data in enumerate(questions_with_available_pairs):
        if q_data["question"]["_id"] == st.session_state.current_question_id:
            selected_question = q_data["question"]
            selected_question_data = q_data
            st.session_state.current_question_index = i
            break
    
    if not selected_question:
        selected_question_data = questions_with_available_pairs[0]
        selected_question = selected_question_data["question"]
        st.session_state.current_question_id = selected_question["_id"]
        st.session_state.current_question_index = 0

    # Navigation entre questions
    if len(questions_with_available_pairs) > 1:
        col_nav = st.columns([2, 5, 2])
        with col_nav[0]:
            if st.button("◀️ Question précédente", 
                        disabled=st.session_state.current_question_index == 0, 
                        use_container_width=True,
                        key=f"btn_prev_question_{st.session_state.current_question_index}"):
                new_index = max(0, st.session_state.current_question_index - 1)
                st.session_state.current_question_index = new_index
                st.session_state.current_question_id = questions_with_available_pairs[new_index]["question"]["_id"]
                st.session_state.current_pair_index = 0
                st.rerun()
        
        with col_nav[1]:
            st.info(f"Question {st.session_state.current_question_index + 1} sur {len(questions_with_available_pairs)}")
        
        with col_nav[2]:
            if st.button("Question suivante ▶️", 
                        disabled=st.session_state.current_question_index >= len(questions_with_available_pairs) - 1, 
                        use_container_width=True,
                        key=f"btn_next_question_{st.session_state.current_question_index}"):
                new_index = min(len(questions_with_available_pairs) - 1, st.session_state.current_question_index + 1)
                st.session_state.current_question_index = new_index
                st.session_state.current_question_id = questions_with_available_pairs[new_index]["question"]["_id"]
                st.session_state.current_pair_index = 0
                st.rerun()

    # Affichage de la question
    st.markdown(f"""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 1.5rem; border-radius: 10px; color: white; margin: 1rem 0;'>
        <h3 style='color: white; margin: 0;'>❓ {selected_question['question']}</h3>
    </div>
    """, unsafe_allow_html=True)

    question_id = selected_question["_id"]
    
    # Obtenir les paires disponibles pour cette question
    available_pairs = get_vote_pairs(question_id, st.session_state.id_navigateur)
    
    if not available_pairs:
        st.info("Vous avez voté sur toutes les paires pour cette question.")
        st.session_state.current_question_index += 1
        if st.session_state.current_question_index < len(questions_with_available_pairs):
            st.session_state.current_question_id = questions_with_available_pairs[st.session_state.current_question_index]["question"]["_id"]
            st.rerun()
        return
    
    # S'assurer que current_pair_index est valide
    if st.session_state.current_pair_index >= len(available_pairs):
        st.session_state.current_pair_index = 0
    
    # Sélectionner la paire actuelle
    current_pair = available_pairs[st.session_state.current_pair_index]
    idea1, idea2 = current_pair
    
    # Navigation entre paires
    if len(available_pairs) > 1:
        pair_cols = st.columns([1, 3, 1])
        with pair_cols[0]:
            if st.button("◀️ Paire précédente", 
                        disabled=st.session_state.current_pair_index == 0, 
                        use_container_width=True,
                        key=f"btn_prev_pair_{st.session_state.current_pair_index}"):
                st.session_state.current_pair_index = max(0, st.session_state.current_pair_index - 1)
                st.rerun()
        
        with pair_cols[1]:
            progress_value = (st.session_state.current_pair_index + 1) / len(available_pairs)
            progress_value = max(0.0, min(1.0, progress_value))
            st.progress(progress_value)
            st.caption(f"Paire {st.session_state.current_pair_index + 1} sur {len(available_pairs)}")
        
        with pair_cols[2]:
            if st.button("Paire suivante ▶️", 
                        disabled=st.session_state.current_pair_index >= len(available_pairs) - 1, 
                        use_container_width=True,
                        key=f"btn_next_pair_{st.session_state.current_pair_index}"):
                st.session_state.current_pair_index = min(len(available_pairs) - 1, st.session_state.current_pair_index + 1)
                st.rerun()

    # Affichage des deux idées pour le vote
    st.markdown("### 🤔 Quelle idée préférez-vous ?")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div style='border: 2px solid #4CAF50; border-radius: 10px; padding: 1.5rem; 
                    height: 100%; background-color: rgba(76, 175, 80, 0.1);'>
        """, unsafe_allow_html=True)
        st.markdown(f"#### 💡 Option A")
        
        type_a = "Idée téléchargée" if idea1.get("creer_par_utilisateur") == "oui" else "Idée originale"
        st.caption(f"Type: {type_a}")
        
        st.markdown(f"**{idea1['idee_texte']}**")
        
        # SUITE DU CODE - À ajouter après la partie 1

        if st.button("✅ Choisir cette idée", 
                    key=f"vote_{question_id}_{str(idea1['_id'])[:10]}_{str(idea2['_id'])[:10]}_b", 
                    use_container_width=True, 
                    type="primary"):
            enregistrer_vote(idea2['_id'], idea1['_id'], question_id)
            
            if st.session_state.current_pair_index < len(available_pairs) - 1:
                st.session_state.current_pair_index += 1
            else:
                st.session_state.current_pair_index = 0
                st.session_state.current_question_index += 1
                if st.session_state.current_question_index < len(questions_with_available_pairs):
                    st.session_state.current_question_id = questions_with_available_pairs[st.session_state.current_question_index]["question"]["_id"]
            
            st.success("✅ Vote enregistré !")
            time.sleep(0.5)
            st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)

    # Bouton "Les deux se valent"
    col_center = st.columns([1, 2, 1])
    with col_center[1]:
        if st.button("🤷 Les deux se valent", 
                    use_container_width=True,
                    key=f"egalite_{question_id}_{str(idea1['_id'])[:10]}_{str(idea2['_id'])[:10]}"):
            enregistrer_vote(idea1['_id'], idea2['_id'], question_id)
            
            if st.session_state.current_pair_index < len(available_pairs) - 1:
                st.session_state.current_pair_index += 1
            else:
                st.session_state.current_pair_index = 0
                st.session_state.current_question_index += 1
                if st.session_state.current_question_index < len(questions_with_available_pairs):
                    st.session_state.current_question_id = questions_with_available_pairs[st.session_state.current_question_index]["question"]["_id"]
            
            st.info("Vote d'égalité enregistré")
            time.sleep(0.5)
            st.rerun()

    # Section pour soumettre une nouvelle idée
    st.markdown("---")
    with st.expander("💡 Proposer une nouvelle idée", expanded=False):
        nouvelle_idee = st.text_area("Votre nouvelle idée :", height=100)
        
        if st.button("➕ Soumettre", key=f"btn_nouvelle_idee_{question_id}"):
            if nouvelle_idee.strip():
                score, label = analyze_sentiment(nouvelle_idee)
                
                db.idees.insert_one({
                    "id_question": question_id,
                    "id_navigateur": st.session_state.id_navigateur,
                    "idee_texte": nouvelle_idee.strip(),
                    "creer_par_utilisateur": "oui",
                    "date_creation": datetime.now(),
                    "sentiment_score": float(score),
                    "sentiment_label": label
                })
                
                update_sentiment_analytics(question_id)
                st.success("✅ Idée ajoutée !")
                time.sleep(1)
                st.rerun()

def enregistrer_vote(gagnant, perdant, question_id):
    """Enregistrer un vote"""
    db = get_db_connection()
    
    if db is None:
        return

    db.vote.insert_one({
        "id_navigateur": st.session_state.id_navigateur,
        "id_question": question_id,
        "id_idee_gagnant": gagnant,
        "id_idee_perdant": perdant,
        "date_vote": datetime.now()
    })

    update_sentiment_analytics(question_id)

def afficher_formulaire_profil():
    """Formulaire de profil utilisateur"""
    db = get_db_connection()
    
    if db is None:
        return

    if db.profil.find_one({"id_navigateur": st.session_state.id_navigateur}):
        return

    with st.expander("📝 Informations démographiques (optionnel)", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            pays = st.text_input("Pays", placeholder="Ex: Sénégal")
            age = st.number_input("Âge", min_value=10, max_value=120, value=25)
        
        with col2:
            sexe = st.selectbox("Genre", ["", "Homme", "Femme", "Autre"])
            fonction = st.text_input("Profession", placeholder="Ex: Étudiant")
        
        if st.button("Enregistrer", key="btn_profil"):
            db.profil.insert_one({
                "id_navigateur": st.session_state.id_navigateur,
                "pays": pays if pays else None,
                "age": age if age else None,
                "sexe": sexe if sexe else None,
                "fonction": fonction if fonction else None,
                "date_creation": datetime.now()
            })
            st.success("✅ Enregistré !")
            time.sleep(1)
            st.rerun()

def afficher_visualisations():
    """Dashboard de visualisations"""
    st.title("📊 Visualisations")
    
    db = get_db_connection()
    
    if db is None:
        st.error("Impossible de charger les données")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Questions", db.question.count_documents({}))
    with col2:
        st.metric("Votes", db.vote.count_documents({}))
    with col3:
        st.metric("Idées", db.idees.count_documents({}))
    with col4:
        st.metric("Participants", db.navigateur.count_documents({}))

def voir_resultats():
    """Affiche les résultats"""
    st.title("📊 Résultats")
    
    db = get_db_connection()
    
    if db is None:
        st.error("Impossible de charger les données")
        return
    
    questions = list(db.question.find({}).sort("date_creation", -1))
    
    if not questions:
        st.info("Aucune question disponible")
        return
    
    question_options = {q['question'][:80]: q['_id'] for q in questions}
    selected = st.selectbox("Question :", list(question_options.keys()))
    question_id = question_options[selected]
    
    pipeline = [
        {"$match": {"id_question": question_id}},
        {"$lookup": {
            "from": "idees",
            "localField": "id_idee_gagnant",
            "foreignField": "_id",
            "as": "idee_gagnant"
        }},
        {"$unwind": "$idee_gagnant"},
        {"$group": {
            "_id": "$idee_gagnant._id",
            "idee": {"$first": "$idee_gagnant.idee_texte"},
            "victoires": {"$sum": 1}
        }},
        {"$sort": {"victoires": -1}}
    ]
    
    resultats = list(db.vote.aggregate(pipeline))
    
    if resultats:
        df = pd.DataFrame(resultats)
        df.columns = ['_id', 'Idée', 'Victoires']
        st.dataframe(df[['Idée', 'Victoires']], use_container_width=True)

def display_home_page():
    """Page d'accueil"""
    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                padding: 4rem 2rem; border-radius: 20px; color: white; text-align: center;'>
        <h1 style='font-size: 3rem; margin-bottom: 1rem;'>🗳️ Wiki Survey - Afrique</h1>
        <p style='font-size: 1.2rem;'>Plateforme citoyenne pour l'avenir de l'Afrique</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("✍️ Créer", use_container_width=True, type="primary"):
            st.session_state.current_tab = "create"
            st.rerun()
    
    with col2:
        if st.button("🗳️ Voter", use_container_width=True):
            st.session_state.current_tab = "vote"
            st.rerun()
    
    with col3:
        if st.button("📊 Résultats", use_container_width=True):
            st.session_state.current_tab = "stats"
            st.rerun()

def main():
    """Fonction principale"""
    
    tabs = ["🏠 Accueil", "➕ Créer", "🗳️ Voter", "📊 Résultats", "📈 Visualisations"]
    tab_keys = ["home", "create", "vote", "stats", "visualisations"]
    
    selected_tab = st.session_state.current_tab
    
    cols = st.columns([1, 1, 1, 1, 1, 2])
    
    for idx, (tab_name, tab_key) in enumerate(zip(tabs, tab_keys)):
        with cols[idx]:
            if st.button(tab_name, 
                        use_container_width=True,
                        type="primary" if selected_tab == tab_key else "secondary",
                        key=f"nav_{tab_key}"):
                st.session_state.current_tab = tab_key
                st.rerun()
    
    with cols[5]:
        if st.session_state.get("email"):
            st.markdown(f"<div style='text-align: right;'>👤 {st.session_state.email}</div>", 
                       unsafe_allow_html=True)
    
    st.markdown("---")
    
    if selected_tab == "home":
        display_home_page()
    elif selected_tab == "create":
        creer_question()
    elif selected_tab == "vote":
        participer()
    elif selected_tab == "stats":
        voir_resultats()
    elif selected_tab == "visualisations":
        afficher_visualisations()

if __name__ == "__main__":
    main()
