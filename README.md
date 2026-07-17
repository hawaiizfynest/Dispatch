# Dispatch

A reading desk for security news.

Dispatch pulls your RSS feeds, folds the same story from six outlets into one entry, and drafts a post you can edit. Then it copies the draft to your clipboard. That is where it stops. You paste it, you post it, you own it.

Written by LJ "HawaiizFynest" Eblacas — Colorado Vista IT Solutions

---

## What it does

**Ingest.** Eighteen security outlets ship configured out of the box: BleepingComputer, The Hacker News, Krebs, The Record, Ars Security, CISA advisories, SANS ISC, Project Zero, Talos, and more. Add your own, disable the noisy ones.

**Dedupe.** When Microsoft ships a zero-day fix, five outlets write it up within an hour. Dispatch collapses those into one entry with every source attached, so you triage the story once instead of five times.

**Triage.** An inbox you can burn through. Star what is worth posting, kill what is not, filter by category or outlet, search the lot.

**Compose.** Pick a story and Dispatch renders a thread title and a body from a template you control. BBCode for forums, Markdown, plain text, or write your own. Edit both in the pane and copy them.

**History.** Mark a story posted and it stays marked. Three weeks later you will not cover it twice.

---

## Installing

You need Python 3.10 or newer.

```
pip install -r requirements.txt
python main.py
```

First launch seeds the feed list and the templates, then opens on an empty inbox. Hit **Refresh feeds** or press F5.

---

## Using it

The window splits three ways. Filters on the left, the story queue in the middle, the story itself on the right.

The queue shows a **Src** count per row. Anything above 1 means several outlets carried it, which is a decent signal that the story has legs.

| Key | Does |
|---|---|
| F5 | Refresh every enabled feed |
| Ctrl+S | Star the selected stories |
| Ctrl+D | Mark posted |
| Del | Kill (hides from the inbox) |
| Ctrl+Return | Open the source article in your browser |
| Ctrl+Shift+T | Copy the thread title |
| Ctrl+Shift+C | Copy the body |

Select several rows and the status keys apply to all of them. Clearing an inbox of forty items takes about a minute.

### The Compose tab

Forums want two things: a thread title and a body. Dispatch drafts both.

The title sits in its own field with a live character count beside it. The count turns amber near your limit and red past it, and the **Trim** button wakes up once you are over. Trimming cuts on a word boundary. Dispatch will not trim behind your back, because a title cut in the wrong place reads worse than a long one.

Set the limit in **File > Settings > Posting**. It ships at 100. Check what your board actually enforces, since forums differ and some truncate without telling you.

The workflow: **Copy title**, paste it, **Copy body**, paste it, post. Use **Copy body and mark posted** for the last one and Dispatch logs it.

Editing the body locks it. Switching templates or hitting **Re-render** rebuilds both fields and throws your edits away.

### Templates

**Templates > Manage templates** opens the editor. Tokens are listed at the bottom of that dialog; double-click one to drop it in.

Every token works in both the title and the body. The ones you will reach for:

| Token | Fills in |
|---|---|
| `{title}` | Headline of the lead article |
| `{facts_bbcode}` | Key facts list: CVEs, CVSS, exploitation, products, scale |
| `{fulltext}` | The whole article. Public domain sources only, empty elsewhere |
| `{items}` | Roundups only: every selected story |
| `{title_short}` | Headline already trimmed to your title limit |
| `{category_tag}` | `[Ransomware] ` with the trailing space, empty when untagged |
| `{cve_suffix}` | ` (CVE-2026-1337)`, empty when there is no CVE **or the headline already has it** |
| `{cve_first}` | Just the first CVE, for when six of them would wreck a title |
| `{summary}` | First few sentences, HTML stripped |
| `{url}` | Lead article link, tracking params removed |
| `{source}` | Outlet name |
| `{cve_list}` | Every CVE ID found across the sources |
| `{cve_line_bbcode}` | A CVE line that disappears when there are no CVEs |
| `{extra_sources_bbcode}` | An "Other coverage" block, empty when only one outlet ran it |
| `{source_count}` | How many outlets carried it |

Tokens Dispatch does not recognize pass through untouched, so `[spoiler]` tags and stray braces survive the render.

`{cve_suffix}` earns its keep. Most outlets already put the CVE in the headline, so a title template of `{title} ({cve_first})` gives you "Microsoft patches Windows zero-day CVE-2026-1337 (CVE-2026-1337)". `{cve_suffix}` checks the headline first and stays empty when the ID is already there. The default title template is `{category_tag}{title}{cve_suffix}`.

---

## Tuning the dedupe

**File > Settings** exposes the knobs.

**Match threshold** (default 82) sets how alike two headlines must be to count as one story. Dispatch scores headline pairs on a blend of two fuzzy ratios and requires at least two words in common.

Raise the threshold and you see the same story twice. Lower it and unrelated stories merge, which buries one of them where you will never read it. The second failure costs more than the first, so the default leans conservative. For reference, "Microsoft patches actively exploited Windows zero-day" and "Google patches actively exploited Chrome zero-day" score 79.4, landing just under the line.

**Compare window** (default 5 days) limits which stories a new article gets compared against. A longer window catches slow-burn coverage. It also drags in last month's Patch Tuesday.

Articles sharing a URL always merge, whatever their headlines say, which catches syndicated copies that got a fresh headline on the way out.

---

## Where your data lives

| OS | Path |
|---|---|
| Windows | `%APPDATA%\Dispatch\` |
| macOS | `~/Library/Application Support/Dispatch/` |
| Linux | `~/.local/share/dispatch/` |

`dispatch.db` holds the stories, `config.json` holds the settings. Delete either one and Dispatch rebuilds it from scratch on next launch. Both are yours. Back up the folder and your triage history travels with you.

**File > Purge old items** clears out articles past the retention window. Starred and posted stories survive a purge regardless of age.

---

## Building a standalone exe

Every tagged version builds itself. Releases carry a ready `Dispatch.exe`, so grab that unless you want to build one yourself.

To build locally:

```
pip install pyinstaller
python tools/version_info.py version_info.txt
python -m PyInstaller --onefile --windowed --name Dispatch --version-file version_info.txt main.py
```

The binary lands in `dist/`. It carries its own Python and its own Qt, so it runs on a machine with neither. The version resource step is optional and only fills in the Windows properties panel; skip it and the exe still runs.

## Cutting a release

Releases are automatic. Tag a commit `v1.0.0` and push it, and the workflow builds the exe, checks it starts, and publishes a release with the binary attached.

In GitHub Desktop:

1. Bump `__version__` in `dispatch/__init__.py` **first**. Do this before anything else. The build compares the tag against it and stops if they disagree, which beats shipping an exe whose About box claims the wrong version.
2. Commit that and push it.
3. Open the **History** tab, right-click the commit you just pushed, and choose **Create Tag**.
4. Name the tag to match the version with a `v` in front: `v1.0.0` for version `1.0.0`.
5. Hit **Push origin**. The tag goes up and the build starts.

Step 1 is first for a reason. GitHub Desktop only deletes tags it has not pushed yet, so a tag that went up against the wrong commit cannot be moved or reused from Desktop at all. Getting out of that means the git command line. Skip the version bump and the cheapest way forward is usually to bump to the next number and tag again, leaving the bad tag to be cleaned up on the web whenever you feel like it. Bumping first costs nothing and avoids the whole thing.

Watch it under the **Actions** tab on GitHub. It takes a few minutes, most of it PyInstaller.

To try a build without releasing anything, open **Actions**, pick **Release**, and use **Run workflow**. That builds the same exe and leaves it as a downloadable artifact, no tag and no release.

A tag with a suffix, `v1.0.0-rc.1`, publishes as a prerelease. `__version__` stays `1.0.0` for those.

---

## Adding a feed

**Feeds > Manage feeds > Add feed**. Paste an RSS or Atom URL. Most outlets link theirs in the page footer.

Uncheck a feed to skip it without losing the stories you already pulled from it. A feed name turns red in the sidebar when its last refresh failed; hover it for the reason.

---

## Roundups

Some threads work better as one post covering ten stories. Select several rows in the queue, pick **Weekly roundup** or **Patch roundup** from the template list, and the post builds from all of them. Whatever you type in the notes box becomes the intro.

## Full text

Dispatch will pull a whole article in for you, but only from US federal agencies. Work produced by a federal agency carries no copyright, so a CISA advisory or an NVD entry is yours to paste whole. The **Fetch full text** button lights up when the source qualifies and stays dark when it does not, and the line beside it tells you which.

Everything else stays summarised. BleepingComputer and Krebs own their prose, and a post built to save readers the click is the exact thing their lawyers write letters about. What you get instead is the **Key facts** block: CVEs with severity, whether anyone is exploiting it, whether CISA listed it, what it affects, how many records went out. Facts carry no copyright and they are the part a security forum actually reads.

## A note on what this is

Dispatch reads, sorts, and drafts. It does not post, and it will not learn to. Title and body both leave through your clipboard, after you read them and decided the story was worth your name.

That constraint is the point. It also means Dispatch does not care where you post. Swap the template and the same queue feeds a forum, a Discord, a blog, a newsletter.

---

## Contributing

Repo: `https://github.com/HawaiizFynest/dispatch`

Clone it with GitHub Desktop, branch off `main`, open a pull request.
