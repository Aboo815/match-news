#!/usr/bin/env ruby
# frozen_string_literal: true

require "json"
require "time"
require "fileutils"
require "optparse"
require "digest"

DEFAULT_STATE_PATH = "/Users/aboo/footballant/7-day-first-google-click/state/match-news-state.json"
REPO_ROOT = File.expand_path("..", __dir__)
PROJECT_ROOT = File.expand_path("../..", __dir__)
PROJECT_RULES_PATH = File.join(PROJECT_ROOT, "PROJECT_RULES.md")
ERROR_LESSONS_PATH = File.join(PROJECT_ROOT, "ERROR_LESSONS.md")
MATCH_DIR = File.join(REPO_ROOT, "matches")

SCORELINES = [
  ["1-0", "2-0", "2-1", "1-1", "0-0", "1-2", "0-1", "2-2"].freeze,
  ["1-0", "2-0", "2-1", "3-1", "1-1", "0-0", "1-2", "0-1"].freeze
].freeze

STRUCTURES = [
  "Goalkeeper; right-back, two centre-backs, left-back; two central midfielders; right winger, attacking midfielder, left winger; centre-forward.",
  "Goalkeeper; back three; wing-backs; two central midfielders; two attackers; centre-forward.",
  "Goalkeeper; back four; one holding midfielder; two central midfielders; two wide forwards; striker.",
  "Goalkeeper; back four; double pivot; two wide attackers; number ten; striker."
].freeze

INTRO_TEMPLATES = [
  "%<home>s vs %<away>s feels like a fixture where rhythm matters more than reputation, because one sloppy spell can decide the tone.",
  "%<home>s vs %<away>s has the shape of a game that turns on the details: second balls, set plays and the moments after turnovers.",
  "%<home>s vs %<away>s arrives with just enough tension to make it uncomfortable for both sides, especially if the first chance goes in.",
  "%<home>s vs %<away>s is the kind of matchup where control and courage have to coexist, because neither team can afford to drift.",
  "%<home>s vs %<away>s looks straightforward on paper, but the game state could swing quickly once the match opens up."
].freeze

MAIN_PARAS = [
  [
    "The predicted %<home>s lineup should prioritise balance: enough security to avoid cheap transitions, but enough forward intent to turn territory into chances.",
    "%<away>s are unlikely to play naïvely. Their expected XI should stay compact, then look to accelerate into space when the home side overcommits.",
    "In %<league>s, these games can change on a single emotional moment. That is why the preview reads less like a talent check and more like a composure test."
  ].freeze,
  [
    "%<home>s will want clean build-up and clear roles, because a messy first half invites the sort of chaotic match they do not control.",
    "%<away>s usually look best when they keep their distances tight and choose their presses carefully. Expect patience rather than constant risk.",
    "The margins feel narrow here. Whoever manages the tense passages after the first swing should earn the better platform."
  ].freeze
].freeze

def usage_and_exit(parser, code: 1)
  warn parser.to_s
  exit(code)
end

def read_required_doc(path)
  raise "Missing required rules file: #{path}" unless File.exist?(path)

  text = File.read(path)
  raise "Required rules file is empty: #{path}" if text.strip.empty?

  text
end

def announce_rule_docs
  [
    ["project_rules", PROJECT_RULES_PATH],
    ["error_lessons", ERROR_LESSONS_PATH]
  ].each do |label, path|
    text = read_required_doc(path)
    headings = text.lines.select { |line| line.start_with?("#") }.first(3).map { |line| line.delete_prefix("#").strip }
    puts "- #{label}: #{path} sha256=#{Digest::SHA256.hexdigest(text)[0, 12]} headings=#{headings.join(' | ')}"
  end
end

def required_base_time(value)
  raise "Missing required --base-time" if value.to_s.strip.empty?

  Time.iso8601(value).getlocal
end

def in_exact_window?(kickoff, base_time, min_hours: 48, max_hours: 72)
  kickoff >= base_time + (min_hours * 3600) && kickoff <= base_time + (max_hours * 3600)
end

def html_escape(text)
  text.to_s
      .gsub("&", "&amp;")
      .gsub("<", "&lt;")
      .gsub(">", "&gt;")
      .gsub('"', "&quot;")
      .gsub("'", "&#39;")
end

def format_date(time)
  time.strftime("%B %-d, %Y")
end

def score_prediction(match_id)
  pool = SCORELINES[match_id.to_i.even? ? 0 : 1]
  pool[match_id.to_i % pool.length]
end

def structure_for(match_id, offset:)
  STRUCTURES[(match_id.to_i + offset) % STRUCTURES.length]
end

def sentence_case_league(league)
  league.to_s.strip
end

def build_match_page(candidate, more_slugs:)
  kickoff = Time.parse(candidate.fetch("kickoff_local"))
  date_str = format_date(kickoff)
  time_str = kickoff.strftime("%H:%M")
  home = candidate.fetch("home")
  away = candidate.fetch("away")
  league = sentence_case_league(candidate.fetch("league"))
  match_id = candidate.fetch("match_id")
  home_team_id = candidate.fetch("home_team_id")
  away_team_id = candidate.fetch("away_team_id")

  title = "#{home} vs #{away} predicted lineup, team news and prediction (#{date_str})"
  description = "#{home} vs #{away} predicted lineup, team news and prediction for #{date_str}, including expected starting XIs and key pre-match context."
  canonical = "https://www.footballant.com/match-news/matches/#{candidate.fetch("slug")}/"

  scoreline = score_prediction(match_id)
  home_goals, away_goals = scoreline.split("-").map(&:to_i)

  intro = format(
    INTRO_TEMPLATES[match_id.to_i % INTRO_TEMPLATES.length],
    home: home,
    away: away
  )

  main_paras = MAIN_PARAS[match_id.to_i % MAIN_PARAS.length].map do |p|
    format(p, home: home, away: away, league: league)
  end

  more_items = more_slugs.map do |slug|
    name = slug.tr("-", " ").gsub(/\bvs\b/i, "vs")
    { slug: slug, label: name }
  end

  <<~HTML
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>#{html_escape(title)}</title>
      <meta name="description" content="#{html_escape(description)}" />
      <meta name="robots" content="index,follow" />
      <link rel="canonical" href="#{html_escape(canonical)}" />
      <link rel="stylesheet" href="../../styles.css" />
    </head>
    <body>
      <main>
        <article>
          <header>
            <h1>#{html_escape(title)}</h1>
            <p>#{html_escape(intro)}</p>
          </header>

          <section>
            <h2>Main Article</h2>
            <p>#{html_escape(main_paras[0])}</p>
            <p>#{html_escape(main_paras[1])}</p>
            <p>#{html_escape(main_paras[2])}</p>
          </section>

          <section>
            <h2>Quick Facts</h2>
            <ul>
              <li><strong>Match:</strong> #{html_escape(home)} vs #{html_escape(away)}</li>
              <li><strong>Competition:</strong> #{html_escape(league)}</li>
              <li><strong>Date:</strong> #{html_escape(date_str)}</li>
              <li><strong>Kick-off:</strong> #{html_escape(time_str)} local time</li>
              <li><strong>Predicted #{html_escape(home)} starting XI structure:</strong> #{html_escape(structure_for(match_id, offset: 0))}</li>
              <li><strong>Predicted #{html_escape(away)} starting XI structure:</strong> #{html_escape(structure_for(match_id, offset: 1))}</li>
              <li><strong>Score prediction:</strong> #{html_escape(home)} #{home_goals}-#{away_goals} #{html_escape(away)}.</li>
            </ul>
          </section>

          <section>
            <h2>Analysis</h2>
            <h3>Team news</h3>
            <p>#{html_escape(home)} should focus on the spine of the team. If they lose the central zones too easily, this turns into a game of repeated recovery runs.</p>
            <p>#{html_escape(away)} will likely prioritise structure and timing. The expected XI is less about surprise and more about limiting the opponent’s clean entries into the box.</p>

            <h3>Match context</h3>
            <p>The first goal would matter, but so would the minutes that follow it. A lead can invite pressure, and this fixture has the profile of a match where swings are sharp.</p>
            <p>If the game stays level into the second half, patience becomes the edge. The side that avoids forcing the next action should see the clearer chances.</p>

            <h3>Prediction</h3>
            <p>The prediction leans toward a narrow margin because both teams have enough strengths to avoid being dominated, yet not quite enough to control every phase.</p>
            <p><strong>Predicted score: #{html_escape(home)} #{home_goals}-#{away_goals} #{html_escape(away)}</strong></p>
          </section>

          <section>
            <h2>Related Coverage on FootballAnt</h2>
            <ul>
              <li><a href="https://www.footballant.com/matches/#{match_id}">Check full AI prediction and latest odds on FootballAnt</a></li>
              <li><a href="https://www.footballant.com/football-data/team/#{home_team_id}">View #{html_escape(home)} detailed team data and recent form</a></li>
              <li><a href="https://www.footballant.com/football-data/team/#{away_team_id}">Explore #{html_escape(away)} performance trends and squad stats</a></li>
              <li><a href="https://www.footballant.com/live-score">Follow live scores and real-time match updates</a></li>
            </ul>
          </section>

          <section>
            <h2>More lineup previews on FootballAnt</h2>
            <ul>
    #{more_items.map { |i| "          <li><a href=\"../#{html_escape(i[:slug])}/\">#{html_escape(i[:label])} predicted lineups and preview</a></li>" }.join("\n")}
            </ul>
          </section>
          <section>
            <h2>More football lineup predictions</h2>
            <ul>
              <li><a href="../../latest-football-lineup-predictions/">Latest football lineup predictions</a></li>
              <li><a href="../../">Football lineup predictions homepage</a></li>
            </ul>
          </section>

          <section>
            <h2>Related Searches</h2>
            <ul>
              <li>#{html_escape(home)} vs #{html_escape(away)} predicted lineup</li>
              <li>#{html_escape(home)} team news vs #{html_escape(away)}</li>
              <li>#{html_escape(away)} predicted lineup vs #{html_escape(home)}</li>
              <li>#{html_escape(home)} vs #{html_escape(away)} prediction</li>
            </ul>
          </section>
        </article>
      </main>
    </body>
    </html>
  HTML
end

def read_file(path)
  File.read(path, encoding: "UTF-8")
end

def write_file(path, content)
  FileUtils.mkdir_p(File.dirname(path))
  File.write(path, content, mode: "w", encoding: "UTF-8")
end

def extract_ol(html, heading_id:)
  marker = %(<h2 id="#{heading_id}")
  idx = html.index(marker)
  raise "Could not find heading #{heading_id}" unless idx

  ol_start = html.index("<ol", idx)
  ol_end = html.index("</ol>", ol_start)
  raise "Could not locate <ol> after #{heading_id}" unless ol_start && ol_end

  [ol_start, ol_end + "</ol>".length]
end

def build_list_items(candidates, href_prefix:, position_start: 1)
  candidates.map.with_index do |c, i|
    pos = position_start + i
    <<~LI.strip
      <li itemprop="itemListElement" itemscope itemtype="https://schema.org/ListItem">
        <a itemprop="item" href="#{href_prefix}#{html_escape(c[:slug])}/"><span itemprop="name">#{html_escape(c[:title])}</span></a>
        <p>Predicted starting XIs, team news and score prediction for this #{html_escape(c[:league])} match.</p>
        <meta itemprop="position" content="#{pos}" />
      </li>
    LI
  end.join("\n")
end

def existing_entry_for_slug(slug)
  path = File.join(MATCH_DIR, slug, "index.html")
  return nil unless File.exist?(path)

  html = read_file(path)
  title = html[/<title>(.*?)<\/title>/m, 1].to_s.strip
  league = html[%r{<li><strong>Competition:</strong>\s*([^<]+)</li>}m, 1].to_s.strip
  return nil if title.empty?

  {
    slug: slug,
    title: title,
    league: league.empty? ? "football" : league
  }
end

def update_latest_lists(repo_root, new_entries, max_items:, page_updated_date:)
  home_path = File.join(repo_root, "index.html")
  latest_path = File.join(repo_root, "latest-football-lineup-predictions", "index.html")

  home_html = read_file(home_path)
  latest_html = read_file(latest_path)

  # Gather existing slugs from each list to preserve order after new inserts.
  home_range = extract_ol(home_html, heading_id: "latest-heading")
  home_ol = home_html[home_range[0]...home_range[1]]
  home_existing = home_ol.scan(%r{href="matches/([^/]+)/"}).flatten

  latest_range = extract_ol(latest_html, heading_id: "article-list-heading")
  latest_ol = latest_html[latest_range[0]...latest_range[1]]
  latest_existing = latest_ol.scan(%r{href="\.\./matches/([^/]+)/"}).flatten

  merged_home = (new_entries.map { |e| e[:slug] } + home_existing).uniq.first(max_items)
  merged_latest = (new_entries.map { |e| e[:slug] } + latest_existing).uniq.first(max_items)

  by_slug = new_entries.each_with_object({}) { |e, acc| acc[e[:slug]] = e }

  merged_home_entries = merged_home.map do |slug|
    by_slug[slug] || existing_entry_for_slug(slug) || { slug: slug, title: slug.tr("-", " ").gsub(/\bvs\b/i, "vs"), league: "football" }
  end

  merged_latest_entries = merged_latest.map do |slug|
    by_slug[slug] || existing_entry_for_slug(slug) || { slug: slug, title: slug.tr("-", " ").gsub(/\bvs\b/i, "vs"), league: "football" }
  end

  home_items = build_list_items(merged_home_entries, href_prefix: "matches/")
  latest_items = build_list_items(merged_latest_entries, href_prefix: "../matches/")

  home_html = home_html.dup
  home_html[home_range[0]...home_range[1]] = "<ol class=\"match-list\">\n#{home_items}\n</ol>"

  latest_html = latest_html.dup
  latest_html[latest_range[0]...latest_range[1]] = "<ol class=\"match-list\">\n#{latest_items}\n</ol>"

  latest_html = latest_html.gsub(
    /<p class="note">Page updated [^<]*<\/p>/,
    "<p class=\"note\">Page updated #{page_updated_date}. The newest upcoming fixtures should stay near the top.</p>"
  )

  write_file(home_path, home_html)
  write_file(latest_path, latest_html)
end

def update_sitemap(repo_root, slugs, lastmod:)
  path = File.join(repo_root, "sitemap.xml")
  xml = read_file(path)
  insert_at = xml.rindex("</urlset>")
  raise "Could not find </urlset> in sitemap.xml" unless insert_at

  existing = xml.scan(%r{<loc>https://www\.footballant\.com/match-news/matches/([^/]+)/</loc>}).flatten.to_h { |s| [s, true] }
  new_slugs = slugs.reject { |s| existing.key?(s) }
  return if new_slugs.empty?

  blocks = new_slugs.map do |slug|
    <<~URL
      <url>
        <loc>https://www.footballant.com/match-news/matches/#{slug}/</loc>
        <lastmod>#{lastmod}</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.8</priority>
      </url>
    URL
  end.join

  xml = xml.dup
  xml.insert(insert_at, blocks)
  write_file(path, xml)
end

options = {
  state_path: DEFAULT_STATE_PATH,
  limit: nil,
  max_items: 60,
  dry_run: false,
  base_time: nil
}

parser = OptionParser.new do |opts|
  opts.banner = "Usage: #{File.basename($PROGRAM_NAME)} [options]"
  opts.on("--state PATH", "Path to match-news-state.json (default: #{DEFAULT_STATE_PATH})") { |v| options[:state_path] = v }
  opts.on("--limit N", Integer, "Limit number of pages generated") { |v| options[:limit] = v }
  opts.on("--max-items N", Integer, "Max items kept in homepage/latest lists (default: 60)") { |v| options[:max_items] = v }
  opts.on("--base-time ISO8601", "Required base time used for exact 48-72h filtering") { |v| options[:base_time] = v }
  opts.on("--dry-run", "Print actions only") { options[:dry_run] = true }
  opts.on("-h", "--help", "Show help") { usage_and_exit(opts, code: 0) }
end

begin
  parser.parse!
rescue OptionParser::ParseError => e
  warn e.message
  usage_and_exit(parser)
end

state_path = options[:state_path]
usage_and_exit(parser) unless File.exist?(state_path)

puts "Rules preflight:"
announce_rule_docs
base_time = required_base_time(options[:base_time])

state = JSON.parse(File.read(state_path))
candidates = state["next_recommended_candidates"] || []

missing = candidates.select do |c|
  slug = c["slug"]
  dir = File.join(MATCH_DIR, slug)
  next false if Dir.exist?(dir)

  kickoff = Time.parse(c.fetch("kickoff_local")) rescue nil
  next false unless kickoff

  in_exact_window?(kickoff, base_time)
end

missing = missing.first(options[:limit]) if options[:limit]

if missing.empty?
  puts "No missing candidates to generate inside exact 48-72 hour window."
  exit(0)
end

missing_by_league = missing.group_by { |c| c["league"].to_s }
generated = []

missing.each do |c|
  slug = c.fetch("slug")
  match_id = c.fetch("match_id").to_i
  home = c.fetch("home")
  away = c.fetch("away")
  league = c.fetch("league")
  kickoff = Time.parse(c.fetch("kickoff_local"))

  title = "#{home} vs #{away} predicted lineup, team news and prediction (#{format_date(kickoff)})"

  more_from_league = (missing_by_league[league.to_s] || []).map { |x| x["slug"] }.reject { |s| s == slug }
  fallback = %w[
    wolves-vs-tottenham-hotspur-lineup-2026
    arsenal-vs-newcastle-united-lineup-2026
    getafe-vs-fc-barcelona-lineup-2026
  ]
  more_slugs = (more_from_league + fallback).uniq.first(3)

  html = build_match_page(c, more_slugs: more_slugs)
  out_path = File.join(MATCH_DIR, slug, "index.html")

  if options[:dry_run]
    puts "[dry-run] write #{out_path}"
  else
    write_file(out_path, html)
  end

  generated << { slug: slug, title: title, league: league, kickoff: kickoff, match_id: match_id }
end

generated.sort_by! { |e| [e[:kickoff], e[:match_id]] }.reverse!

if options[:dry_run]
  puts "[dry-run] update homepage + latest lists (#{generated.length} new)"
  puts "[dry-run] update sitemap.xml (#{generated.length} new)"
else
  page_updated_date = base_time.strftime("%Y-%m-%d")
  update_latest_lists(REPO_ROOT, generated, max_items: options[:max_items], page_updated_date: page_updated_date)
  update_sitemap(REPO_ROOT, generated.map { |e| e[:slug] }, lastmod: page_updated_date)
end

puts "Generated #{generated.length} page(s):"
generated.each { |e| puts "- #{e[:slug]} (#{e[:league]})" }
