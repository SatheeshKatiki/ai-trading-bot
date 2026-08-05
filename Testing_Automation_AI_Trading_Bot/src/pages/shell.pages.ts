/**
 * Page objects for the screens whose current coverage is "it renders, it is
 * reachable, and it survives a backend failure".
 *
 * They are deliberately thin. Writing speculative locators for widgets no
 * spec asserts on yet produces page objects that drift out of date silently —
 * each of these gains real methods when a spec needs one, and until then the
 * shared `BasePage` behaviour (route, root, readiness, navigation) is exactly
 * what the navigation and resilience suites need.
 */
import type { Page } from '@playwright/test';
import { AppRoutes, type AppRoute } from '@config/routes';
import { BasePage } from '@core/base-page';
import { HeaderComponent } from '@pages/components/header.component';
import { SidebarComponent } from '@pages/components/sidebar.component';

abstract class ShellPage extends BasePage {
  readonly sidebar: SidebarComponent;
  readonly header: HeaderComponent;

  constructor(page: Page) {
    super(page);
    this.sidebar = new SidebarComponent(page);
    this.header = new HeaderComponent(page);
  }
}

export class LiveTradingPage extends ShellPage {
  readonly name = 'Live Trading';
  protected readonly route: AppRoute = AppRoutes.liveTrading;
  protected readonly rootTestId = 'live-page';
}

export class BacktestPage extends ShellPage {
  readonly name = 'Backtesting';
  protected readonly route: AppRoute = AppRoutes.backtest;
  protected readonly rootTestId = 'backtest-page';
}

export class SignalsPage extends ShellPage {
  readonly name = 'AI Signals';
  protected readonly route: AppRoute = AppRoutes.signals;
  protected readonly rootTestId = 'signals-page';
}

export class StrategyPage extends ShellPage {
  readonly name = 'Strategy Settings';
  protected readonly route: AppRoute = AppRoutes.strategy;
  protected readonly rootTestId = 'strategy-page';
}

export class OptionsDeskPage extends ShellPage {
  readonly name = 'Options Desk';
  protected readonly route: AppRoute = AppRoutes.optionsDesk;
  protected readonly rootTestId = 'options-page';
}

export class AnalyticsPage extends ShellPage {
  readonly name = 'Analytics';
  protected readonly route: AppRoute = AppRoutes.analytics;
  protected readonly rootTestId = 'analytics-page';
}

export class BrokerPage extends ShellPage {
  readonly name = 'Broker Settings';
  protected readonly route: AppRoute = AppRoutes.broker;
  protected readonly rootTestId = 'broker-page';
}

export class RiskPage extends ShellPage {
  readonly name = 'Risk Management';
  protected readonly route: AppRoute = AppRoutes.risk;
  protected readonly rootTestId = 'risk-page';
}

export class SettingsPage extends ShellPage {
  readonly name = 'Settings';
  protected readonly route: AppRoute = AppRoutes.settings;
  protected readonly rootTestId = 'settings-page';
}

export class DocsPage extends ShellPage {
  readonly name = 'Documentation';
  protected readonly route: AppRoute = AppRoutes.docs;
  protected readonly rootTestId = 'docs-page';
}

export class AboutPage extends ShellPage {
  readonly name = 'About';
  protected readonly route: AppRoute = AppRoutes.about;
  protected readonly rootTestId = 'about-page';
}
