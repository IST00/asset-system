import type { KekeCharacter } from '@/types'

/**
 * 21 fixed characters from the Keke universe. Ported from H5 § CHARACTERS.
 * Order matters: the home page splits this in half across two marquee rows.
 */
export const CHARACTERS: KekeCharacter[] = [
  { name: '爸爸', file: '爸爸.png', role: '奶牛猫', group: '核心家庭', desc: '家里最大的"大孩子"，陪玩起来比孩子还嗨' },
  { name: '妈妈', file: '妈妈.png', role: '三花猫', group: '核心家庭', desc: '干练的职业女性，一回家就成了孩子最温柔的陪伴' },
  { name: '呼噜', file: '呼噜.png', role: '哥哥 · 6岁', group: '核心家庭', desc: '鲁莽率真护妹妹，虽然偶尔、偶尔也会被妹妹气到炸毛' },
  { name: '可可', file: '可可.png', role: '妹妹 · 4岁', group: '核心家庭', desc: '甜酷萌妹，关键时刻总能蹦出让大人愣住的话' },
  { name: '跳跳', file: '跳跳.png', role: '小袋鼠', group: '玩伴', desc: '永远在蹦，排队也蹦，吃饭也蹦' },
  { name: '团团', file: '团团.png', role: '小刺猬', group: '玩伴', desc: '一害羞就缩成球，但很快又自己打开' },
  { name: '亮亮', file: '亮亮.png', role: '小萤火虫', group: '玩伴', desc: '晚上屁股会发光，是大家的"小夜灯"' },
  { name: '飞飞', file: '飞飞.png', role: '小蝙蝠', group: '玩伴', desc: '爱倒挂在各种地方，觉得超好玩' },
  { name: '落落', file: '落落.png', role: '小蜗牛', group: '玩伴', desc: '动作很慢，但每次最后一名也很开心' },
  { name: '豆豆', file: '豆豆.png', role: '小仓鼠', group: '玩伴', desc: '嘴硬胆小，总说"我才不怕"然后躲到可可背后' },
  { name: '阿橙', file: '阿橙.png', role: '橘猫', group: '玩伴', desc: '圆滚滚乐天派，聊什么都能绕回"好好吃哦"' },
  { name: '米卡', file: '米卡.png', role: '小兔子', group: '玩伴', desc: '一百个主意，九个出问题，剩一个是天才' },
  { name: '卡皮巴拉一家', file: '卡皮巴拉家.png', role: '邻居', group: '玩伴', desc: '胖乎乎超淡定的邻居，最小那只总抱着一个小果子' },
  { name: '熊猫先生', file: '熊猫先生.png', role: '书店老板', group: '城市大人', desc: '知道所有答案，但回答你总是再问你一个问题' },
  { name: '老虎先生', file: '老虎先生.png', role: '警察', group: '城市大人', desc: '高大威严脸上一颗痣，其实非常怕虫子' },
  { name: '仓鼠爷爷', file: '仓鼠爷爷.png', role: '医生', group: '城市大人', desc: '小白大褂老花镜，得坐高凳子才能跟病人平视' },
  { name: '狐狸小姐', file: '狐狸小姐.png', role: '售货员', group: '城市大人', desc: '笑眯眯戴手套，公认城里最漂亮的人' },
  { name: '大象奶奶', file: '大象奶奶.png', role: '公交司机', group: '城市大人', desc: '开车超慢从不急，座位底下永远藏着饼干' },
  { name: '长颈鹿小姐', file: '长颈鹿小姐.png', role: '幼儿园老师', group: '城市大人', desc: '低头跟小朋友说话，时不时撞到吊灯' },
  { name: '企鹅先生', file: '企鹅先生.png', role: '冰激凌店老板', group: '城市大人', desc: '总戴围巾，做的冰激凌不会化太快' },
  { name: '猫头鹰教授', file: '猫头鹰教授.png', role: '天文台台长', group: '城市大人', desc: '白天打瞌睡，讲星星讲到一半可能睡着' },
]
