"""
Référentiel de compétences et de secteurs orienté tech / industrie.  [D5]
Normalise les variantes (« Qt5 », « Qt 5.15 », « QtQuick ») et repère les compétences
et le secteur d'une fiche de poste.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .text import norm

# (libellé, catégorie, alias…)
_SKILLS: list[tuple[str, str, list[str]]] = [
    # Langages
    ("C++", "langages", ["c++", "cpp", "c plus plus"]),
    ("C++11", "langages", ["c++11"]), ("C++14", "langages", ["c++14"]), ("C++17", "langages", ["c++17"]),
    ("C++20", "langages", ["c++20"]), ("C", "langages", ["langage c", "ansi c", "c99", "c ansi"]),
    ("C#", "langages", ["c#", "csharp", "c sharp"]), ("Java", "langages", ["java", "java 8", "java 11", "java 17", "java 21"]),
    ("Kotlin", "langages", ["kotlin"]), ("Python", "langages", ["python", "python3", "python 3"]),
    ("JavaScript", "langages", ["javascript", "js", "ecmascript"]), ("TypeScript", "langages", ["typescript"]),
    ("Go", "langages", ["golang", "go lang"]), ("Rust", "langages", ["rust"]), ("Ada", "langages", ["ada", "ada 95", "ada 2012"]),
    ("Fortran", "langages", ["fortran"]), ("VHDL", "langages", ["vhdl"]), ("Verilog", "langages", ["verilog"]),
    ("SQL", "langages", ["sql", "pl/sql", "plsql", "t-sql"]), ("Bash", "langages", ["bash", "shell", "scripts shell"]),
    ("QML", "langages", ["qml", "qt quick", "qtquick", "qt quick controls"]), ("PHP", "langages", ["php"]),
    ("Scala", "langages", ["scala"]), ("MATLAB", "langages", ["matlab"]), ("Simulink", "outils", ["simulink"]),
    # Frameworks
    ("Qt", "frameworks", ["qt", "qt4", "qt 4", "qt widgets", "qtwidgets", "qt framework"]),
    ("Qt 5", "frameworks", ["qt5", "qt 5", "qt 5.15"]), ("Qt 6", "frameworks", ["qt6", "qt 6"]),
    ("Boost", "frameworks", ["boost"]), ("STL", "frameworks", ["stl"]), ("Eclipse RCP", "frameworks", ["eclipse rcp", "rcp"]),
    ("Spring Boot", "frameworks", ["spring boot", "springboot"]), ("Spring", "frameworks", ["spring", "spring framework"]),
    ("Hibernate", "frameworks", ["hibernate", "jpa"]), ("React", "frameworks", ["react", "reactjs", "react.js"]),
    ("Angular", "frameworks", ["angular", "angularjs"]), ("Vue.js", "frameworks", ["vue", "vuejs", "vue.js"]),
    (".NET", "frameworks", [".net", "dotnet", ".net core", "asp.net"]), ("Django", "frameworks", ["django"]),
    ("FastAPI", "frameworks", ["fastapi"]), ("Flask", "frameworks", ["flask"]), ("Node.js", "frameworks", ["node", "nodejs", "node.js"]),
    ("ROS", "frameworks", ["ros", "ros2", "robot operating system"]), ("OpenGL", "frameworks", ["opengl", "opengl es"]),
    ("Vulkan", "frameworks", ["vulkan"]), ("GTest", "frameworks", ["gtest", "google test", "googletest"]),
    ("Kafka", "frameworks", ["kafka", "apache kafka"]), ("gRPC", "frameworks", ["grpc"]), ("DDS", "frameworks", ["dds", "opendds", "rti dds"]),
    # Outils
    ("Git", "outils", ["git", "gitlab", "github", "bitbucket"]), ("GitLab CI", "outils", ["gitlab ci", "gitlab-ci"]),
    ("Jenkins", "outils", ["jenkins"]), ("CMake", "outils", ["cmake"]), ("Make", "outils", ["make", "makefile"]),
    ("Conan", "outils", ["conan"]), ("Docker", "outils", ["docker"]), ("Kubernetes", "outils", ["kubernetes", "k8s"]),
    ("Terraform", "outils", ["terraform"]), ("Ansible", "outils", ["ansible"]), ("Jira", "outils", ["jira"]),
    ("Confluence", "outils", ["confluence"]), ("SonarQube", "outils", ["sonar", "sonarqube"]), ("Valgrind", "outils", ["valgrind"]),
    ("GDB", "outils", ["gdb"]), ("Visual Studio", "outils", ["visual studio"]), ("Qt Creator", "outils", ["qt creator", "qtcreator"]),
    ("DOORS", "outils", ["doors", "ibm doors"]), ("Polarion", "outils", ["polarion"]), ("SCADE", "outils", ["scade"]),
    ("Rhapsody", "outils", ["rhapsody", "ibm rhapsody"]), ("Enterprise Architect", "outils", ["enterprise architect"]),
    ("ClearCase", "outils", ["clearcase"]), ("SVN", "outils", ["svn", "subversion"]), ("Prometheus", "outils", ["prometheus"]),
    ("Grafana", "outils", ["grafana"]),
    # Systèmes / cloud / bases
    ("Linux", "systemes", ["linux", "unix", "debian", "ubuntu", "red hat", "rhel", "centos"]),
    ("Linux embarqué", "systemes", ["linux embarque", "yocto", "buildroot", "embedded linux"]),
    ("Windows", "systemes", ["windows"]), ("RTOS", "systemes", ["rtos", "freertos", "vxworks", "integrity", "pikeos", "qnx"]),
    ("AWS", "cloud", ["aws", "amazon web services"]), ("Azure", "cloud", ["azure"]), ("GCP", "cloud", ["gcp", "google cloud"]),
    ("PostgreSQL", "bases", ["postgresql", "postgres"]), ("Oracle", "bases", ["oracle"]), ("MySQL", "bases", ["mysql", "mariadb"]),
    ("MongoDB", "bases", ["mongodb", "mongo"]), ("SQLite", "bases", ["sqlite"]), ("Redis", "bases", ["redis"]),
    # Normes (industrie)
    ("DO-178C", "normes", ["do-178c", "do178c", "do 178c", "do-178", "do178", "do-178b", "ed-12c"]),
    ("DO-254", "normes", ["do-254", "do254"]), ("ARP4754A", "normes", ["arp4754", "arp 4754", "arp4754a"]),
    ("ISO 26262", "normes", ["iso 26262", "iso26262"]), ("IEC 61508", "normes", ["iec 61508", "cei 61508"]),
    ("EN 50128", "normes", ["en 50128", "en50128", "cenelec"]), ("IEC 62304", "normes", ["iec 62304"]),
    ("MISRA C", "normes", ["misra", "misra c", "misra c++"]), ("AUTOSAR", "normes", ["autosar"]),
    ("IEC 61131", "normes", ["iec 61131", "iec61131"]), ("ISO 27001", "normes", ["iso 27001"]),
    # Méthodes
    ("Agile Scrum", "methodes", ["agile", "scrum", "kanban"]), ("Cycle en V", "methodes", ["cycle en v", "v-cycle"]),
    ("TDD", "methodes", ["tdd", "test driven"]), ("UML", "methodes", ["uml", "sysml"]), ("CI/CD", "methodes", ["ci/cd", "integration continue", "devops"]),
    ("IHM", "methodes", ["ihm", "hmi", "interface homme machine", "interfaces homme-machine", "gui"]),
    ("Temps réel", "methodes", ["temps reel", "real-time", "real time"]), ("Multithreading", "methodes", ["multithread", "multithreading", "concurrence"]),
]

SECTORS: dict[str, list[str]] = {
    "Aéronautique": ["aeronautique", "avionique", "airbus", "cockpit", "aerien", "aviation", "safran", "thales avionics", "dassault aviation"],
    "Spatial": ["spatial", "satellite", "cnes", "ariane", "space"],
    "Défense": ["defense", "militaire", "naval", "armement", "dga"],
    "Énergie": ["energie", "energeticien", "edf", "nucleaire", "centrale", "reseau electrique", "engie", "rte", "supervision"],
    "Navigation aérienne": ["navigation aerienne", "dsna", "controle aerien", "atm", "espace aerien"],
    "Ferroviaire": ["ferroviaire", "sncf", "alstom", "signalisation", "metro", "rail"],
    "Automobile": ["automobile", "automotive", "constructeur automobile", "adas", "renault", "stellantis"],
    "Médical": ["medical", "sante", "dispositif medical", "hopital"],
    "Banque / Finance": ["banque", "bancaire", "finance", "assurance", "assureur", "paiement"],
    "Télécom": ["telecom", "operateur", "5g", "reseau mobile"],
    "Industrie": ["industrie", "industriel", "usine", "automate", "scada", "production"],
}


@lru_cache(maxsize=1)
def _alias_index() -> list[tuple[re.Pattern, str, str]]:
    idx = []
    for label, cat, aliases in _SKILLS:
        for a in sorted(set([label, *aliases]), key=len, reverse=True):
            na = norm(a)
            if not na:
                continue
            pat = re.compile(rf"(?<![a-z0-9+#.]){re.escape(na)}(?![a-z0-9+#])")
            idx.append((pat, label, cat))
    idx.sort(key=lambda x: len(x[0].pattern), reverse=True)
    return idx


def canonical(label: str) -> tuple[str, str]:
    """Libellé + catégorie normalisés ; inconnu → tel quel, catégorie « autres »."""
    n = norm(label)
    for label_, cat, aliases in _SKILLS:
        if n == norm(label_) or n in (norm(a) for a in aliases):
            return label_, cat
    return label.strip(), "autres"


def find_in_text(text: str) -> list[str]:
    """Compétences du référentiel citées dans un texte (ordre d'apparition, sans doublon)."""
    t = " " + norm(text) + " "
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for pat, label, _ in _alias_index():
        for m in pat.finditer(t):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), label))
    seen, out = set(), []
    for _, label in sorted(found):
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def family(label: str) -> set[str]:
    """Libellés équivalents pour le matching (Qt 6 ⊂ Qt, C++17 ⊂ C++…)."""
    out = {label}
    if label.startswith("Qt"):
        out |= {"Qt", "Qt 5", "Qt 6", "QML"}
    if label.startswith("C++"):
        out |= {"C++", "C++11", "C++14", "C++17", "C++20"}
    if label in ("Spring", "Spring Boot"):
        out |= {"Spring", "Spring Boot"}
    return out


def detect_sectors(text: str) -> list[str]:
    t = " " + norm(text) + " "
    scores = {s: sum(len(re.findall(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t)) for k in kws) for s, kws in SECTORS.items()}
    return [s for s, v in sorted(scores.items(), key=lambda x: -x[1]) if v > 0]


def category_of(label: str) -> str:
    return canonical(label)[1]
