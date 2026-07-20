# -*- coding: utf-8 -*-
# `consignment_effect` used to be declared here. It moved to nfe_xml, which owns
# the nfe.cfop model.
#
# Why: soc_settlement reads the effect (to rebuild a shelf from the fiscal
# history) and soc_settlement does NOT depend on soc_audit -- soc_audit depends
# on IT. The inverted dependency only survived because everything happened to be
# loaded by the time anything ran; it broke the moment a stored field had to be
# computed during soc_settlement's own module load, before soc_audit existed.
#
# What stays in soc_audit is what actually belongs to the audit: the
# classification DATA (data/nfe_cfop_consignment_data.xml) and the settings
# screen where a human maps a newly-seen CFOP (views/nfe_cfop_views.xml).
