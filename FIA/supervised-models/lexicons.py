INTENT_KEYWORDS = {
    # Portuguese (PT/BR) + English
    "elogio": {
        "pt": [
            "parabéns", "obrigado", "excelente", "incrível", "adoro", "gosto muito",
            "ótimo", "maravilhoso", "perfeito", "bom trabalho", "top"
        ],
        "en": [
            "great", "awesome", "amazing", "love", "excellent", "fantastic", "nice",
            "well done", "thank you", "thanks", "brilliant"
        ],
    },
    "reclamacao": {
        "pt": [
            "não funciona", "nao funciona", "erro", "bug", "pior", "horrível", "horrivel",
            "odeio", "insuportável", "insuportavel", "decepcionado", "reembolso", "enganoso",
            "problema", "travou", "crashou", "lento", "demorado"
        ],
        "en": [
            "doesn't work", "doesnt work", "not working", "broken", "crash", "bug",
            "slow", "worst", "hate", "refund", "scam", "misleading", "issue", "problem",
            "annoying", "drag", "delay"
        ],
    },
    "sugestao": {
        "pt": [
            "poderiam", "podia", "deveria", "seria bom", "sugiro", "sugestão", "sugestao",
            "adicionem", "podiam", "melhorem", "considerem"
        ],
        "en": [
            "should", "could", "would be nice", "please add", "i suggest", "suggestion",
            "consider", "feature request", "improve"
        ],
    },
    "suporte": {
        "pt": [
            "ajuda", "como faço", "como faco", "como usar", "alguém sabe", "alguem sabe",
            "não consigo", "nao consigo", "duvida", "dúvida", "suporte", "onde encontro",
            "pode explicar"
        ],
        "en": [
            "help", "how do i", "how to", "can someone", "anyone know", "support",
            "where can i", "please explain", "question", "how can i"
        ],
    },
}

PROFANITY_WORDS = set(
    w.lower() for w in [
        # English
        "idiot", "stupid", "moron", "dumb", "loser", "trash", "garbage", "crap",
        "asshole", "bitch", "bastard", "shit", "fuck", "fucking", "wtf", "suck",
        "sucks", "douche", "retard", "retarded", "kill yourself", "kys", "die",
        # Portuguese
        "idiota", "burro", "estúpido", "estupido", "merda", "lixo", "bosta",
        "porra", "caralho", "imbecil", "otário", "otario", "pqp",
    ]
)

INSULT_PATTERNS = [
    "you are", "you're", "youre", "tu és", "tu es", "você é", "voce e",
]

THREAT_WORDS = set(
    w.lower() for w in [
        "threat", "report you", "sue", "lawsuit", "ban you", "kill", "hurt", "destroy",
        "ameaça", "ameaca", "processo", "denunciar", "banir"
    ]
)

SARCASM_CUES = [
    "yeah right", "as if", "sure", "totally", "love that for me", "amazing...",
    "great...", "awesome...", "thanks for nothing", "what a genius", "nice job",
]

