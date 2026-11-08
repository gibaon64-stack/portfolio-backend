from app.extensions import db
from app.models import JourneyEntry, Profile, Service


PROFILE_INTRODUCTION = (
    "Hello, I'm Ian Mabruk. A software engineer, technology enthusiast, entrepreneur "
    "and digital solutions developer passionate about transforming ideas into practical "
    "digital experiences. My journey into technology began with curiosity and a desire to "
    "understand how software works and how technology can solve everyday challenges. "
    "Through my software engineering journey at Moringa School, I developed experience "
    "in building applications, developing websites, working with databases, designing "
    "digital solutions and solving real-world problems through code. Today, through "
    "Mabrixel Technologies, I bring ideas to life by helping individuals, startups and "
    "businesses build meaningful digital products."
)

HERO_DESCRIPTION = (
    "Welcome to Mabrixel Technologies, a world where dreams evolve into reality. "
    "Come, let's build together the software of your dreams: technology designed to "
    "solve your everyday problems and transform your ideas into reality."
)

JOURNEY_ENTRIES = [
    (
        "Discovering Technology",
        "EARLY CURIOSITY",
        "Curiosity about computers, software, and digital innovation grew into an interest in how technology can solve everyday challenges.",
    ),
    (
        "Starting My Coding Journey",
        "LEARNING TO BUILD",
        "Learning programming fundamentals and practicing problem-solving created the foundation for turning ideas into working software.",
    ),
    (
        "Software Development at Moringa School",
        "MORINGA SCHOOL",
        "Software development training covered programming fundamentals, frontend and backend development, databases, full-stack applications, and collaborative engineering practices.",
    ),
    (
        "Building Practical Applications",
        "FROM CONCEPT TO PRODUCT",
        "Practice moved toward functional applications, connecting interfaces, APIs, databases, and deployment to address practical needs.",
    ),
    (
        "Entrepreneurship with Mabrixel",
        "BUILDING A TECHNOLOGY BUSINESS",
        "Mabrixel Technologies brings software development and business problem-solving together to help people turn ideas into digital products.",
    ),
    (
        "Looking Ahead",
        "CONTINUOUS GROWTH",
        "The next chapter is about continuing to grow as an engineer and contributing useful, well-crafted technology to a wider community.",
    ),
]

SERVICES = [
    (
        "Software Engineering",
        "Custom software designed around specific business challenges and operational needs.",
        [
            "Custom business software",
            "Business automation",
            "API development and integration",
            "Database architecture",
            "Enterprise software solutions",
            "Software maintenance",
        ],
    ),
    (
        "Website Development",
        "Professional websites and web applications built to support businesses and their customers.",
        [
            "Corporate and business websites",
            "Portfolio websites",
            "E-commerce platforms",
            "Landing pages",
            "Custom web applications",
            "Website maintenance and optimization",
        ],
    ),
    (
        "Mobile Application Development",
        "Modern mobile applications for businesses and startups across common mobile platforms.",
        [
            "Android applications",
            "iOS applications",
            "Cross-platform applications",
            "Business applications",
            "Application integrations",
            "Maintenance and updates",
        ],
    ),
    (
        "Digital Marketing",
        "Digital presence and marketing support shaped around a business's audience and goals.",
        [
            "Social media management",
            "Digital advertising",
            "Search engine optimization",
            "Brand visibility",
            "Marketing strategy",
            "Content and campaign management",
        ],
    ),
]

MARKETING_PACKAGES = [
    {
        "name": "BRONZE",
        "price": 12000,
        "description": "A KES 12,000 package. Confirm the included platforms and service scope before booking.",
        "included_services": [],
        "platform_count": None,
        "content_details": "",
        "management_details": "",
    },
    {
        "name": "SILVER",
        "price": 16000,
        "description": "A KES 16,000 package. Confirm the included platforms and service scope before booking.",
        "included_services": [],
        "platform_count": None,
        "content_details": "",
        "management_details": "",
    },
    {
        "name": "GOLD",
        "price": 22000,
        "description": "A KES 22,000 package. Confirm the included platforms and service scope before booking.",
        "included_services": [],
        "platform_count": None,
        "content_details": "",
        "management_details": "",
    },
]


def seed_content():
    if not Profile.query.first():
        db.session.add(Profile(
            name="Ian Mabruk",
            introduction=PROFILE_INTRODUCTION,
            hero_description=HERO_DESCRIPTION,
            location="Kenya",
        ))

    existing_journey = {entry.title for entry in JourneyEntry.query.all()}
    for position, (title, period, description) in enumerate(JOURNEY_ENTRIES):
        if title not in existing_journey:
            db.session.add(JourneyEntry(
                title=title,
                period=period,
                description=description,
                position=position,
            ))

    existing_services = {service.title for service in Service.query.all()}
    for position, (title, description, capabilities) in enumerate(SERVICES):
        if title not in existing_services:
            db.session.add(Service(
                title=title,
                description=description,
                capabilities=capabilities,
                position=position,
            ))

    marketing_service = Service.query.filter_by(title="Digital Marketing").first()
    if marketing_service:
        pricing = dict(marketing_service.pricing or {})
        if "packages" not in pricing:
            pricing["packages"] = MARKETING_PACKAGES
            marketing_service.pricing = pricing

    db.session.commit()