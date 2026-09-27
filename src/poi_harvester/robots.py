"""Robots path matching with wildcards, end anchors and longest-rule priority.

Nonstandard unrooted provider patterns are honored conservatively as substrings.
This avoids treating a provider's explicit exclusion as permission to fetch.
"""
import re
from urllib.parse import quote, urlsplit


def _octets(value):
    value = quote(value, safe="/%?:@!$&'()*+,;=-._~")
    def normalize(match):
        number = int(match.group()[1:], 16)
        char = chr(number)
        return char if char.isascii() and (char.isalnum() or char in '-._~') else f'%{number:02X}'
    return re.sub(r'%[0-9a-fA-F]{2}', normalize, value)


def allowed(lines, user_agent, url):
    groups, agents, rules = [], [], []
    for line in list(lines) + ['User-agent: __end__']:
        key, sep, value = line.split('#', 1)[0].strip().partition(':')
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == 'user-agent':
            if rules:
                groups.append((agents, rules))
                agents, rules = [], []
            agents.append(value.lower())
        elif key in ('allow', 'disallow') and agents:
            rules.append((value, key == 'allow'))
    if agents:
        groups.append((agents, rules))
    token = user_agent.split('/', 1)[0].split()[0].lower()
    specific = [(a, r) for a, r in groups if any(x != '*' and x in token for x in a)]
    selected = specific or [(a, r) for a, r in groups if '*' in a]
    parts = urlsplit(url)
    path = _octets((parts.path or '/') + ('?' + parts.query if parts.query else ''))
    if parts.path == '/robots.txt':
        return True
    matches = []
    for _, rules in selected:
        for raw, permit in rules:
            if not raw:
                continue
            pattern = _octets(raw)
            anchor = pattern.endswith('$')
            if anchor:
                pattern = pattern[:-1]
            expression = re.escape(pattern).replace(r'\*', '.*')
            prefix = '^' if pattern.startswith('/') else '^.*'
            if re.match(prefix + expression + ('$' if anchor else ''), path):
                matches.append((len(pattern.replace('*', '').encode()), permit))
    return max(matches)[1] if matches else True
