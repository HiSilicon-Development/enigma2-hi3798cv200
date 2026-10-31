"""
Reject transponder records with frequency 0 from entering or persisting in
the channel db.

Failure chain observed on dvbip-1002 (2026-11-06): the DTMB frontend lost
signal intermittently, getTransponderData then reported frequency 0, e2 fed
that feparm back through addChannelToList (clobbering the good in-memory
record) and saveServicelist persisted "t 0:0:5:..." into lamedb.  Every
later start then tuned to 0 kHz (kernel: "frontend 0 frequency 0 out of
range") until lamedb was hand-repaired.

Guard 1 (addChannelToList): drop feparm updates with frequency 0 so a
  broken frontend read cannot clobber a good record.
Guard 2 (saveServicelist): skip persisting any channel whose frequency is 0
  so memory pollution can never reach the disk.

Both lamedb v4 and v5 loaders pass transponders through addChannelToList;
the save guard precedes output to either format. Leave the existing parsers,
service serialization and dangling-bouquet repair unchanged.
"""

p = 'lib/dvb/db.cpp'
s = open(p, encoding='utf-8').read()

# ---- Guard 1: addChannelToList ----
old1 = """RESULT eDVBDB::addChannelToList(const eDVBChannelID &id, iDVBFrontendParameters *feparm)
{
\tchannel ch;
\tstd::map<eDVBChannelID, channel>::iterator it = m_channels.find(id);
\tASSERT(feparm);
\tch.m_frontendParameters = feparm;
"""
new1 = """RESULT eDVBDB::addChannelToList(const eDVBChannelID &id, iDVBFrontendParameters *feparm)
{
\tchannel ch;
\tstd::map<eDVBChannelID, channel>::iterator it = m_channels.find(id);
\tASSERT(feparm);
\t/* a broken frontend can report frequency 0; keep the previous record */
\t{
\t\teDVBFrontendParametersSatellite sat;
\t\teDVBFrontendParametersTerrestrial ter;
\t\teDVBFrontendParametersCable cab;
\t\teDVBFrontendParametersATSC atsc;
\t\tunsigned int freqchk;
\t\tif (!feparm->getDVBS(sat)) freqchk = sat.frequency;
\t\telse if (!feparm->getDVBT(ter)) freqchk = ter.frequency;
\t\telse if (!feparm->getDVBC(cab)) freqchk = cab.frequency;
\t\telse if (!feparm->getATSC(atsc)) freqchk = atsc.frequency;
\t\telse freqchk = 1; /* unknown delivery system: don't judge */
\t\tif (freqchk == 0)
\t\t{
\t\t\teDebug("[eDVBDB] addChannelToList: reject %08x:%04x:%04x, frequency 0 from frontend", id.dvbnamespace.get(), id.transport_stream_id.get(), id.original_network_id.get());
\t\t\treturn -1;
\t\t}
\t}
\tch.m_frontendParameters = feparm;
"""
if s.count(old1) == 1:
    s = s.replace(old1, new1, 1)
    print('addChannelToList freq-0 guard inserted')
elif s.count(new1) == 1:
    print('addChannelToList guard already present')
else:
    raise SystemExit('addChannelToList anchor not found - upstream changed, review needed')

# ---- Guard 2: saveServicelist, before the chid fprintf ----
old2 = """\t\tconst eDVBChannelID &chid = i->first;
\t\tconst channel &ch = i->second;

\t\tfprintf(f, "%08x:%04x:%04x\\n", chid.dvbnamespace.get(),
"""
new2 = """\t\tconst eDVBChannelID &chid = i->first;
\t\tconst channel &ch = i->second;

\t\t/* never persist transponders with frequency 0 (broken frontend data) */
\t\t{
\t\t\teDVBFrontendParametersSatellite sat;
\t\t\teDVBFrontendParametersTerrestrial ter;
\t\t\teDVBFrontendParametersCable cab;
\t\t\teDVBFrontendParametersATSC atsc;
\t\t\tunsigned int freqchk;
\t\t\tif (!ch.m_frontendParameters->getDVBS(sat)) freqchk = sat.frequency;
\t\t\telse if (!ch.m_frontendParameters->getDVBT(ter)) freqchk = ter.frequency;
\t\t\telse if (!ch.m_frontendParameters->getDVBC(cab)) freqchk = cab.frequency;
\t\t\telse if (!ch.m_frontendParameters->getATSC(atsc)) freqchk = atsc.frequency;
\t\t\telse freqchk = 1;
\t\t\tif (freqchk == 0)
\t\t\t{
\t\t\teDebug("[eDVBDB] saveServicelist: skip %08x:%04x:%04x, frequency 0 (omitted from lamedb output)", chid.dvbnamespace.get(), chid.transport_stream_id.get(), chid.original_network_id.get());
\t\t\t\tcontinue;
\t\t\t}
\t\t}

\t\tfprintf(f, "%08x:%04x:%04x\\n", chid.dvbnamespace.get(),
"""
if s.count(old2) == 1:
    s = s.replace(old2, new2, 1)
    print('saveServicelist freq-0 guard inserted')
elif s.count(new2) == 1:
    print('saveServicelist guard already present')
else:
    raise SystemExit('saveServicelist anchor not found - upstream changed, review needed')

open(p, 'w', encoding='utf-8').write(s)
