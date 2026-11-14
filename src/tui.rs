use crate::{catalog, store::Store};
use anyhow::{Result, ensure};
use crossterm::{
    event::{
        self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyEventKind, MouseEventKind,
    },
    execute,
};
use ratatui::{
    layout::{Constraint, Layout},
    style::{Color, Style, Stylize},
    widgets::{Block, Borders, List, ListItem, ListState, Paragraph, Wrap},
};
use std::{
    io::{self, IsTerminal},
    time::Duration,
};

struct Restore;
impl Drop for Restore {
    fn drop(&mut self) {
        let _ = execute!(io::stdout(), DisableMouseCapture);
        ratatui::restore();
    }
}
pub fn run(store: &Store, mouse: bool) -> Result<()> {
    ensure!(
        io::stdin().is_terminal() && io::stdout().is_terminal(),
        "Use a terminal for interactive mode, or kagnode status --json"
    );
    let settings = store.settings()?;
    let managed = store.managed_root();
    let mut terminal = ratatui::init();
    let _restore = Restore;
    if mouse {
        execute!(io::stdout(), EnableMouseCapture)?;
    }
    let mut selected = 0usize;
    let mut folder = None::<usize>;
    let mut nav = ListState::default();
    let mut search = String::new();
    let mut searching = false;
    loop {
        let entries: Vec<_> = catalog::PRODUCTS
            .iter()
            .enumerate()
            .filter(|(_, p)| p.name.to_lowercase().contains(&search.to_lowercase()))
            .collect();
        selected = selected.min(entries.len().saturating_sub(1));
        nav.select((!entries.is_empty()).then_some(selected));
        terminal.draw(|f| {
            let vertical=Layout::vertical([Constraint::Length(3),Constraint::Min(4),Constraint::Length(2)]).split(f.area());
            f.render_widget(Paragraph::new("KagNode. Daemon").bold().block(Block::default().borders(Borders::BOTTOM)),vertical[0]);
            let columns=Layout::horizontal([Constraint::Percentage(32),Constraint::Percentage(68)]).split(vertical[1]);
            let rows=entries.iter().map(|(_,p)|ListItem::new(format!(" {}  {}",if catalog::installed(managed,p){"●"}else{"○"},p.name)));
            f.render_stateful_widget(List::new(rows).block(Block::default().title(if searching{format!("Search: {search}")}else{"Applications".into()}).borders(Borders::ALL)).highlight_style(Style::default().fg(Color::LightBlue).bg(Color::DarkGray)).highlight_symbol("› "),columns[0],&mut nav);
            let text=if let Some(index)=folder {
                let p=&catalog::PRODUCTS[index];format!("← Back to applications\n\nKagNode. {}\n\nRepository: every-lemon/{}\nInstalled state: {}\n\nManagement\n  Overview and health\n  Configuration and review\n  Logs and audit\n  Updates and backups\n  High availability\n\nHA durable state: {}\n\nUse the command interface for reviewed configuration changes. No service is changed by browsing this folder.",p.name,p.repository,if catalog::installed(managed,p){"detected; run health inspection"}else{"not detected"},p.ha_state)
            } else {format!("Your KagNode workspace\n\nProfile: {:?}\nWeb dashboard: {}\n\nSelect an application and press Enter.\n\nInstalled services retain their existing data and native ownership. HA activation requires qualified networking, fencing, quorum and replication.\n\nCommands\n  kagnode status --json\n  kagnode settings show\n  kagnode ha plan --file cluster.json\n  kagnode serve",settings.profile,if settings.web_enabled{"enabled"}else{"disabled"})};
            f.render_widget(Paragraph::new(text).wrap(Wrap{trim:false}).block(Block::default().title("Workspace").borders(Borders::ALL)),columns[1]);
            f.render_widget(Paragraph::new("↑↓ Navigate  Enter Open  ←/Esc Back  / Search  q Quit").fg(Color::Gray),vertical[2]);
        })?;
        if !event::poll(Duration::from_millis(250))? {
            continue;
        }
        match event::read()? {
            Event::Key(k) if k.kind == KeyEventKind::Press => match k.code {
                KeyCode::Esc => {
                    folder = None;
                    searching = false;
                    search.clear();
                }
                KeyCode::Char('q') if !searching => break,
                KeyCode::Char('/') if !searching => {
                    searching = true;
                    folder = None;
                }
                KeyCode::Char(c) if searching => {
                    search.push(c);
                    selected = 0;
                }
                KeyCode::Backspace if searching => {
                    search.pop();
                    selected = 0;
                }
                KeyCode::Up => selected = selected.saturating_sub(1),
                KeyCode::Down => selected = (selected + 1).min(entries.len().saturating_sub(1)),
                KeyCode::Enter | KeyCode::Right => {
                    folder = entries.get(selected).map(|(i, _)| *i);
                    searching = false;
                }
                KeyCode::Left => folder = None,
                _ => {}
            },
            Event::Mouse(m) if mouse => match m.kind {
                MouseEventKind::ScrollUp => selected = selected.saturating_sub(1),
                MouseEventKind::ScrollDown => {
                    selected = (selected + 1).min(entries.len().saturating_sub(1))
                }
                MouseEventKind::Down(event::MouseButton::Left) => {
                    let area = terminal.size()?;
                    if m.column < area.width * 32 / 100 && m.row >= 4 {
                        let index = usize::from(m.row - 4);
                        if index < entries.len() {
                            selected = index;
                            folder = Some(entries[index].0);
                        }
                    }
                }
                _ => {}
            },
            _ => {}
        }
    }
    Ok(())
}
