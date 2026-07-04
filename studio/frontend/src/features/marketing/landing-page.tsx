import {
  ArrowRight,
  BookOpenText,
  Boxes,
  BrainCircuit,
  Braces,
  Check,
  ChevronRight,
  Cloud,
  Cpu,
  Database,
  FileSearch,
  GitBranch,
  GraduationCap,
  KeyRound,
  Layers3,
  LibraryBig,
  LockKeyhole,
  Network,
  Search,
  ServerCog,
  ShieldCheck,
  Sparkles,
  TestTube2,
  Workflow,
} from "lucide-react";
import { Link } from "@tanstack/react-router";
import type { CSSProperties, ComponentType, ReactNode } from "react";
import "./landing-page.css";

const basePath = import.meta.env.BASE_URL;
const asset = (path: string) => `${basePath}${path}`;

type FeatureCard = {
  title: string;
  description: string;
  icon: ComponentType<{ className?: string; strokeWidth?: number }>;
};

const coreFeatures: FeatureCard[] = [
  {
    title: "Chat privé",
    description: "Des conversations sécurisées avec isolation complète de vos données.",
    icon: LockKeyhole,
  },
  {
    title: "Entrainement de modèles",
    description: "Entrainez vos modèles localement ou via des ressources cloud supervisées.",
    icon: GraduationCap,
  },
  {
    title: "RAG documentaire",
    description: "Exploitez vos documents avec la génération augmentée par récupération.",
    icon: FileSearch,
  },
  {
    title: "Gouvernance entreprise",
    description: "Controlez les accès, les traces d'audit et les usages par équipe.",
    icon: ShieldCheck,
  },
];

const nativeModules: FeatureCard[] = [
  {
    title: "Cost Optimizer",
    description: "Choisissez automatiquement le meilleur fournisseur selon le budget et la tâche.",
    icon: Cpu,
  },
  {
    title: "Dataset Builder",
    description: "Transformez projets et documents en jeux de données prêts pour le fine-tuning.",
    icon: LibraryBig,
  },
  {
    title: "Context Heatmap",
    description: "Visualisez les zones utiles du contexte avant d'envoyer une requête couteuse.",
    icon: Search,
  },
  {
    title: "Codex intégré",
    description: "Un espace de chat dédié aux modèles de code, avec raisonnement préconfiguré.",
    icon: Braces,
  },
  {
    title: "Training cloud",
    description: "Préparez des runs Kaggle, Colab ou cloud quand la machine locale ne suffit pas.",
    icon: Cloud,
  },
  {
    title: "Providers hybrides",
    description: "Basculez entre OpenAI, Ollama, Hugging Face et vos endpoints privés.",
    icon: ServerCog,
  },
];

const workflowSteps = [
  {
    number: "01",
    title: "Connectez vos données",
    body: "Branchez vos sources de données, fichiers, bases et services en gardant la main sur les accès.",
    icons: [Database, Cloud, BookOpenText, Layers3],
  },
  {
    number: "02",
    title: "Construisez votre recette",
    body: "Composez et testez vos pipelines d'IA avec des blocs lisibles, versionnés et réutilisables.",
    icons: [TestTube2, Sparkles, Workflow, Braces],
  },
  {
    number: "03",
    title: "Restez propriétaire",
    body: "Vos données, vos modèles, vos décisions. CogniX orchestre sans confisquer.",
    icons: [KeyRound, ShieldCheck, Boxes, Network],
  },
];

const plans = [
  {
    name: "Local",
    price: "Open source",
    description: "Pour créer, tester et discuter avec vos modèles sur votre machine.",
    points: ["Chat privé", "Ollama et GGUF", "Recettes visuelles", "Hub de modèles"],
  },
  {
    name: "Pro",
    price: "Beta",
    description: "Pour mixer local, API et training cloud avec plus d'automatisation.",
    points: ["Providers externes", "Dataset Builder", "Cost Optimizer", "Codex intégré"],
  },
  {
    name: "Business",
    price: "Sur mesure",
    description: "Pour les équipes qui veulent gouvernance, conformité et traçabilité.",
    points: ["Roles et accès", "Audit complet", "Déploiement dédié", "Support prioritaire"],
  },
];

function SectionEyebrow({ children }: { children: ReactNode }) {
  return <p className="marketing-eyebrow">{children}</p>;
}

function MarketingHeader() {
  return (
    <header className="marketing-header">
      <Link to="/" className="marketing-brand" aria-label="Accueil CogniX">
        <img src={asset("cognix-logo.png")} alt="" className="marketing-brand-logo" />
        <span className="marketing-brand-name">CogniX</span>
        <span className="marketing-brand-by">by EbkAI</span>
      </Link>
      <nav className="marketing-nav" aria-label="Navigation principale">
        <a href="#features">Fonctionnalités</a>
        <a href="#documentation">Documentation</a>
        <a href="#pricing">Tarifs</a>
      </nav>
      <Link to="/login" className="marketing-login">
        Se connecter
      </Link>
    </header>
  );
}

function ProductWindow() {
  return (
    <div className="marketing-product-window">
      <img
        src={asset("marketing/cognix-recipe-editor.png")}
        alt="Interface de recette visuelle CogniX"
        className="marketing-product-image"
      />
    </div>
  );
}

function FeatureTile({ feature, index }: { feature: FeatureCard; index: number }) {
  const Icon = feature.icon;
  return (
    <article className="marketing-tile marketing-reveal" style={{ "--delay": `${index * 70}ms` } as CSSProperties}>
      <span className="marketing-icon-shell">
        <Icon className="size-8" strokeWidth={1.75} />
      </span>
      <div>
        <h3>{feature.title}</h3>
        <p>{feature.description}</p>
      </div>
    </article>
  );
}

function WorkflowDiagram({ icons }: { icons: Array<FeatureCard["icon"]> }) {
  return (
    <div className="marketing-diagram" aria-hidden="true">
      {icons.map((Icon, index) => (
        <span key={index} className="marketing-diagram-node">
          <Icon className="size-6" strokeWidth={1.6} />
        </span>
      ))}
      <span className="marketing-diagram-lock">
        <LockKeyhole className="size-7" strokeWidth={1.7} />
      </span>
      <span className="marketing-diagram-output">
        <Check className="size-5" />
        Deploiement
      </span>
    </div>
  );
}

function PlanCard({ plan, index }: { plan: (typeof plans)[number]; index: number }) {
  return (
    <article className="marketing-plan marketing-reveal" style={{ "--delay": `${index * 90}ms` } as CSSProperties}>
      <div>
        <p>{plan.name}</p>
        <h3>{plan.price}</h3>
        <span>{plan.description}</span>
      </div>
      <ul>
        {plan.points.map((point) => (
          <li key={point}>
            <Check className="size-4" />
            {point}
          </li>
        ))}
      </ul>
    </article>
  );
}

export function MarketingLandingPage() {
  return (
    <div className="marketing-page">
      <MarketingHeader />

      <section className="marketing-hero" aria-labelledby="marketing-hero-title">
        <div className="marketing-hero-copy marketing-reveal">
          <h1 id="marketing-hero-title">
            Construisez votre IA.
            <br />
            Chez vous.
          </h1>
          <p>
            CogniX est le studio open source pour créer, connecter et déployer des IA
            modulaires en toute autonomie.
          </p>
          <div className="marketing-hero-actions">
            <Link to="/signup" className="marketing-primary">
              Rejoindre la beta
            </Link>
            <a
              href="https://github.com/kamkam308/CogniX-v1-beta"
              target="_blank"
              rel="noreferrer"
              className="marketing-secondary"
            >
              <GitBranch className="size-6" />
              Voir sur GitHub
            </a>
          </div>
        </div>
        <img
          src={asset("marketing/cognix-hero-network.png")}
          alt=""
          className="marketing-hero-network"
        />
      </section>

      <section id="features" className="marketing-section marketing-features">
        <SectionEyebrow>Fonctionnalités</SectionEyebrow>
        <h2>Un studio complet</h2>
        <div className="marketing-feature-grid">
          <article className="marketing-studio-panel marketing-reveal">
            <div className="marketing-panel-heading">
              <span className="marketing-icon-shell">
                <Workflow className="size-8" strokeWidth={1.75} />
              </span>
              <div>
                <h3>Studio de recettes visuel</h3>
                <p>Concevez, testez et déployez des workflows IA avec notre éditeur visuel intuitif.</p>
              </div>
            </div>
            <ProductWindow />
          </article>

          <article className="marketing-hub-panel marketing-reveal" style={{ "--delay": "110ms" } as CSSProperties}>
            <div className="marketing-panel-heading">
              <span className="marketing-icon-shell">
                <Boxes className="size-8" strokeWidth={1.75} />
              </span>
              <div>
                <h3>Hub de modèles</h3>
                <p>Accédez, comparez et utilisez les meilleurs modèles du marché en un clic.</p>
              </div>
            </div>
            <img
              src={asset("marketing/cognix-model-hub.png")}
              alt="Grille de modèles CogniX"
              className="marketing-hub-image"
            />
          </article>

          {coreFeatures.map((feature, index) => (
            <FeatureTile key={feature.title} feature={feature} index={index + 2} />
          ))}
        </div>
      </section>

      <section id="documentation" className="marketing-section marketing-workflow-section">
        <SectionEyebrow>Comment ça marche</SectionEyebrow>
        <div className="marketing-workflow-list">
          {workflowSteps.map((step, index) => (
            <article className="marketing-workflow-row marketing-reveal" key={step.number} style={{ "--delay": `${index * 100}ms` } as CSSProperties}>
              <span className="marketing-step-number">{step.number}</span>
              <div className="marketing-step-copy">
                <h2>{step.title}</h2>
                <p>{step.body}</p>
              </div>
              <WorkflowDiagram icons={step.icons} />
            </article>
          ))}
        </div>
      </section>

      <section className="marketing-section marketing-native-section">
        <div className="marketing-section-split">
          <div>
            <SectionEyebrow>Modules natifs</SectionEyebrow>
            <h2>Les nouveaux outils sont intégrés au coeur de CogniX.</h2>
          </div>
          <p>
            Pas de surcouche fragile : les capacités avancées suivent la même logique que le chat,
            les projets et le hub, pour rester maintenables dans le code source.
          </p>
        </div>
        <div className="marketing-native-grid">
          {nativeModules.map((feature, index) => (
            <FeatureTile key={feature.title} feature={feature} index={index} />
          ))}
        </div>
      </section>

      <section className="marketing-foundations">
        <div className="marketing-foundations-frame marketing-reveal">
          <h2>Construit sur des fondations ouvertes</h2>
          <div className="marketing-foundation-logos" aria-label="Technologies ouvertes utilisées par CogniX">
            <span>
              <Boxes className="size-12" />
              ONNX
            </span>
            <span>
              <Network className="size-12" />
              Pydantic
            </span>
            <span>
              <BrainCircuit className="size-12" />
              LangChain
            </span>
            <span>
              <Sparkles className="size-12" />
              LiteLLM
            </span>
            <span>
              <Braces className="size-12" />
              JSON
            </span>
          </div>
          <div className="marketing-open-actions">
            <span>AGPL-3.0 Open Source</span>
            <a href="https://github.com/kamkam308/CogniX-v1-beta" target="_blank" rel="noreferrer">
              <GitBranch className="size-8" />
              Voir le code source
            </a>
          </div>
        </div>
      </section>

      <section id="pricing" className="marketing-section marketing-pricing">
        <div className="marketing-section-split">
          <div>
            <SectionEyebrow>Tarifs</SectionEyebrow>
            <h2>Choisissez le niveau qui correspond à votre usage.</h2>
          </div>
          <p>
            La configuration au premier lancement peut activer un profil particulier,
            développeur ou entreprise, avec les outils adaptés à chaque plan.
          </p>
        </div>
        <div className="marketing-plan-grid">
          {plans.map((plan, index) => (
            <PlanCard key={plan.name} plan={plan} index={index} />
          ))}
        </div>
      </section>

      <section className="marketing-final-cta">
        <h2>Déployez un studio IA que vous pouvez vraiment posséder.</h2>
        <div className="marketing-hero-actions">
          <Link to="/signup" className="marketing-primary">
            Rejoindre la beta
          </Link>
          <a href="#features" className="marketing-secondary">
            Explorer les fonctionnalités
            <ArrowRight className="size-5" />
          </a>
        </div>
      </section>

      <footer className="marketing-footer">
        <span>CogniX by EbkAI</span>
        <a href="#features">
          Fonctionnalités
          <ChevronRight className="size-4" />
        </a>
      </footer>
    </div>
  );
}
