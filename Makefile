.PHONY: prod-upgrade prod-nuke

prod-upgrade:
	./deploy.sh upgrade

prod-nuke:
	./deploy.sh nuke
