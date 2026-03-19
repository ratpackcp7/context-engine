{% if stale_count > 0 %}⚠️ *{{ stale_count }} stale item{{ "s" if stale_count != 1 else "" }}:*
{% for item in stale_items %}• {{ item.project_name }}: {{ item.content }} ({{ item.staleness_days }}d)
{% endfor %}{% else %}✅ *No stale items*
{% endif %}{% if new_blockers %}
🚫 *{{ new_blockers | length }} new blocker{{ "s" if new_blockers | length != 1 else "" }}:*
{% for b in new_blockers %}• {{ b.project_name }}: {{ b.content }}
{% endfor %}{% else %}
📋 0 new blockers{% endif %}